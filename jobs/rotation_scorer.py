# jobs/rotation_scorer.py
"""
Signal Rotation Scorer

Evaluates whether an incoming signal is strong enough to justify rotating out of
an existing underperforming position.  Used by both the paper trading system and
the live (Alpaca) position monitor.

Rotation Philosophy:
- Only rotate when portfolio is at or near capacity (no empty slots).
- The incoming signal must be meaningfully stronger than the weakest position.
- Underperforming or stagnant positions are rotation candidates.
- A cooldown prevents excessive churn (turnover drag ~0.3% round-trip).
- Never rotate out of positions that are hitting stop/TP thresholds — those
  are handled by the normal exit logic.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class RotationCandidate:
    """Holds the evaluation data for a single rotation candidate."""

    def __init__(
        self,
        ticker: str,
        entry_price: float,
        current_price: float,
        signal_score: float,
        days_held: int,
        sector: str = 'Unknown',
        multi_signal_tier: str = 'none',
        trailing_enabled: bool = False,
    ):
        self.ticker = ticker
        self.entry_price = entry_price
        self.current_price = current_price
        self.signal_score = signal_score
        self.days_held = days_held
        self.sector = sector
        self.multi_signal_tier = multi_signal_tier
        self.trailing_enabled = trailing_enabled

        # Derived
        self.pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0

    @property
    def effective_score(self) -> float:
        """
        Decay the original signal score based on current performance.

        A position that is losing money or stagnant has a lower effective score
        than its entry signal score suggested.  This makes it easier for a new
        high-conviction signal to displace it.

        Formula:
            effective = signal_score + pnl_adjustment + time_decay
        """
        score = self.signal_score

        # P&L adjustment: losing positions get penalised, winners get a boost
        if self.pnl_pct < -5.0:
            score += self.pnl_pct * 0.3          # e.g. -7% → -2.1
        elif self.pnl_pct < 0:
            score += self.pnl_pct * 0.15          # e.g. -3% → -0.45
        elif self.pnl_pct > 10.0:
            score += min(self.pnl_pct * 0.1, 3.0) # cap winner bonus at +3

        # Time decay: positions held > 14 days without meaningful gains erode
        if self.days_held > 14 and self.pnl_pct < 5.0:
            time_penalty = min((self.days_held - 14) * 0.1, 2.0)
            score -= time_penalty

        return max(score, 0.0)

    def __repr__(self):
        return (
            f"RotationCandidate({self.ticker}, score={self.signal_score:.1f}, "
            f"eff={self.effective_score:.1f}, pnl={self.pnl_pct:+.1f}%, "
            f"days={self.days_held})"
        )


class RotationScorer:
    """
    Decides whether to rotate out of a position in favour of a new signal.

    Parameters are injected at construction so both jobs/config.py and
    automated_trading/config.py can supply their own values.
    """

    def __init__(
        self,
        enable_rotation: bool = True,
        min_incoming_score: float = 10.0,
        score_advantage_threshold: float = 4.0,
        max_position_pnl_for_rotation: float = 5.0,
        min_days_held_for_rotation: int = 3,
        rotation_cooldown_hours: int = 48,
        max_rotations_per_day: int = 2,
        protect_trailing_stops: bool = True,
        protect_positive_momentum: bool = True,
        positive_momentum_threshold: float = 8.0,
    ):
        self.enable_rotation = enable_rotation
        self.min_incoming_score = min_incoming_score
        self.score_advantage_threshold = score_advantage_threshold
        self.max_position_pnl_for_rotation = max_position_pnl_for_rotation
        self.min_days_held_for_rotation = min_days_held_for_rotation
        self.rotation_cooldown_hours = rotation_cooldown_hours
        self.max_rotations_per_day = max_rotations_per_day
        self.protect_trailing_stops = protect_trailing_stops
        self.protect_positive_momentum = protect_positive_momentum
        self.positive_momentum_threshold = positive_momentum_threshold

        # Track rotation events to enforce cooldown and daily limits
        self._rotation_history: List[Dict] = []

    # --------------------------------------------------------------------- #
    #  Public API
    # --------------------------------------------------------------------- #

    def find_rotation_target(
        self,
        incoming_signal: Dict,
        positions: Dict[str, Dict],
        get_current_price_fn,
        max_positions: int,
    ) -> Optional[Tuple[str, Dict, Dict]]:
        """
        Determine if an incoming signal should replace an existing position.

        Args:
            incoming_signal: New signal dict (must have 'ticker', 'signal_score',
                             'entry_price', optionally 'sector', 'multi_signal_tier').
            positions: Current portfolio positions dict {ticker: pos_dict}.
            get_current_price_fn: Callable(ticker, fallback) -> float.
            max_positions: Maximum allowed concurrent positions.

        Returns:
            Tuple of (exit_ticker, exit_position, incoming_signal) if rotation is
            warranted, or None if no rotation should occur.
        """
        if not self.enable_rotation:
            return None

        # Only rotate when at or near capacity
        if len(positions) < max_positions:
            return None

        incoming_score = incoming_signal.get('signal_score', 0)
        incoming_ticker = incoming_signal.get('ticker', '')

        # Gate 1: incoming signal must meet minimum quality bar
        if incoming_score < self.min_incoming_score:
            logger.debug(
                f"Rotation skip: {incoming_ticker} score {incoming_score:.1f} "
                f"< min {self.min_incoming_score}"
            )
            return None

        # Gate 2: daily rotation limit
        if self._rotations_today() >= self.max_rotations_per_day:
            logger.info(
                f"Rotation skip: daily limit reached ({self.max_rotations_per_day})"
            )
            return None

        # Gate 3: cooldown check
        if self._in_cooldown():
            logger.debug("Rotation skip: cooldown active")
            return None

        # Build candidate list from current positions
        candidates = []
        for ticker, pos in positions.items():
            # Don't rotate into a ticker we already hold
            if ticker == incoming_ticker:
                continue

            current_price = get_current_price_fn(ticker, pos['entry_price'])
            entry_date = pos.get('entry_date', datetime.now())
            if isinstance(entry_date, str):
                try:
                    entry_date = datetime.fromisoformat(entry_date)
                except (ValueError, TypeError):
                    entry_date = datetime.now()

            days_held = (datetime.now() - entry_date).days

            candidate = RotationCandidate(
                ticker=ticker,
                entry_price=pos['entry_price'],
                current_price=current_price,
                signal_score=pos.get('signal_score', 0),
                days_held=days_held,
                sector=pos.get('sector', 'Unknown'),
                multi_signal_tier=pos.get('multi_signal_tier', 'none'),
                trailing_enabled=pos.get('trailing_enabled', False),
            )
            candidates.append(candidate)

        if not candidates:
            return None

        # Filter out positions that should be protected
        eligible = [c for c in candidates if self._is_eligible_for_rotation(c)]

        if not eligible:
            logger.debug("Rotation skip: no eligible positions to rotate out of")
            return None

        # Sort by effective score ascending (weakest first)
        eligible.sort(key=lambda c: c.effective_score)
        weakest = eligible[0]

        # Gate 4: the new signal must have a meaningful score advantage
        advantage = incoming_score - weakest.effective_score
        if advantage < self.score_advantage_threshold:
            logger.debug(
                f"Rotation skip: {incoming_ticker} advantage {advantage:.1f} "
                f"< threshold {self.score_advantage_threshold} "
                f"(incoming {incoming_score:.1f} vs {weakest.ticker} eff {weakest.effective_score:.1f})"
            )
            return None

        logger.info(
            f"ROTATION CANDIDATE: Replace {weakest.ticker} "
            f"(eff_score={weakest.effective_score:.1f}, pnl={weakest.pnl_pct:+.1f}%, "
            f"days={weakest.days_held}) with {incoming_ticker} "
            f"(score={incoming_score:.1f}, advantage=+{advantage:.1f})"
        )

        return (weakest.ticker, positions[weakest.ticker], incoming_signal)

    def record_rotation(self, exited_ticker: str, entered_ticker: str) -> None:
        """Record a rotation event for cooldown and daily-limit tracking."""
        self._rotation_history.append({
            'exited': exited_ticker,
            'entered': entered_ticker,
            'timestamp': datetime.now(),
        })

    def get_rotation_stats(self) -> Dict:
        """Return rotation statistics for reporting."""
        today_rotations = self._rotations_today()
        total_rotations = len(self._rotation_history)
        last_rotation = self._rotation_history[-1] if self._rotation_history else None
        return {
            'total_rotations': total_rotations,
            'rotations_today': today_rotations,
            'max_per_day': self.max_rotations_per_day,
            'cooldown_hours': self.rotation_cooldown_hours,
            'in_cooldown': self._in_cooldown(),
            'last_rotation': last_rotation,
        }

    # --------------------------------------------------------------------- #
    #  Internal helpers
    # --------------------------------------------------------------------- #

    def _is_eligible_for_rotation(self, candidate: RotationCandidate) -> bool:
        """Check whether a position can be rotated out."""
        # Must have been held for a minimum number of days
        if candidate.days_held < self.min_days_held_for_rotation:
            return False

        # Protect positions with active trailing stops (they're winning)
        if self.protect_trailing_stops and candidate.trailing_enabled:
            return False

        # Protect positions with strong positive momentum
        if (self.protect_positive_momentum
                and candidate.pnl_pct >= self.positive_momentum_threshold):
            return False

        # Only rotate out positions that are underperforming
        if candidate.pnl_pct > self.max_position_pnl_for_rotation:
            return False

        return True

    def _rotations_today(self) -> int:
        """Count rotations performed today."""
        today = datetime.now().date()
        return sum(
            1 for r in self._rotation_history
            if r['timestamp'].date() == today
        )

    def _in_cooldown(self) -> bool:
        """Check if we're in a post-rotation cooldown period."""
        if not self._rotation_history:
            return False
        last = self._rotation_history[-1]['timestamp']
        return datetime.now() - last < timedelta(hours=self.rotation_cooldown_hours)


# --------------------------------------------------------------------------- #
#  Factory helpers: build a RotationScorer from the appropriate config module
# --------------------------------------------------------------------------- #

def build_paper_rotation_scorer():
    """Build a RotationScorer using jobs/config.py settings."""
    try:
        import config as cfg
    except ImportError:
        from jobs import config as cfg

    return RotationScorer(
        enable_rotation=getattr(cfg, 'ENABLE_SIGNAL_ROTATION', True),
        min_incoming_score=getattr(cfg, 'ROTATION_MIN_INCOMING_SCORE', 10.0),
        score_advantage_threshold=getattr(cfg, 'ROTATION_SCORE_ADVANTAGE_THRESHOLD', 4.0),
        max_position_pnl_for_rotation=getattr(cfg, 'ROTATION_MAX_POSITION_PNL', 5.0),
        min_days_held_for_rotation=getattr(cfg, 'ROTATION_MIN_DAYS_HELD', 3),
        rotation_cooldown_hours=getattr(cfg, 'ROTATION_COOLDOWN_HOURS', 48),
        max_rotations_per_day=getattr(cfg, 'ROTATION_MAX_PER_DAY', 2),
        protect_trailing_stops=getattr(cfg, 'ROTATION_PROTECT_TRAILING', True),
        protect_positive_momentum=getattr(cfg, 'ROTATION_PROTECT_MOMENTUM', True),
        positive_momentum_threshold=getattr(cfg, 'ROTATION_MOMENTUM_THRESHOLD', 8.0),
    )


def build_live_rotation_scorer():
    """Build a RotationScorer using automated_trading/config.py settings."""
    from automated_trading import config as cfg

    return RotationScorer(
        enable_rotation=getattr(cfg, 'ENABLE_SIGNAL_ROTATION', True),
        min_incoming_score=getattr(cfg, 'ROTATION_MIN_INCOMING_SCORE', 10.0),
        score_advantage_threshold=getattr(cfg, 'ROTATION_SCORE_ADVANTAGE_THRESHOLD', 4.0),
        max_position_pnl_for_rotation=getattr(cfg, 'ROTATION_MAX_POSITION_PNL', 5.0),
        min_days_held_for_rotation=getattr(cfg, 'ROTATION_MIN_DAYS_HELD', 3),
        rotation_cooldown_hours=getattr(cfg, 'ROTATION_COOLDOWN_HOURS', 48),
        max_rotations_per_day=getattr(cfg, 'ROTATION_MAX_PER_DAY', 2),
        protect_trailing_stops=getattr(cfg, 'ROTATION_PROTECT_TRAILING', True),
        protect_positive_momentum=getattr(cfg, 'ROTATION_PROTECT_MOMENTUM', True),
        positive_momentum_threshold=getattr(cfg, 'ROTATION_MOMENTUM_THRESHOLD', 8.0),
    )

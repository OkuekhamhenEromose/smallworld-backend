"""
Django management command: audit_stale_rewards
Assessment Q8 implementation.

Design principles:
- Dry-run by default; --fix required for writes.
- Transaction safety: all updates in a single atomic block.
- Memory safety: use iterator() for large result sets.
- Structured logging: every expired ID logged at INFO.
- Idempotency: re-running --fix on already-expired rewards is safe.
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.rewards.models import Reward

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Audit stale claimed rewards (claimed > 7 days ago). "
        "Dry-run by default; use --fix to update records."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            dest="fix",
            default=False,
            help="Actually update eligible records to 'expired'. Without this, dry-run only.",
        )

    def handle(self, *args, **options):
        dry_run = not options["fix"]
        cutoff_date = timezone.now() - timedelta(days=7)

        # Build queryset: claimed rewards older than 7 days
        stale_qs = Reward.objects.filter(
            status=Reward.STATUS_CLAIMED,
            claimed_at__lt=cutoff_date,
        ).order_by("reward_type", "id")

        # Gather summary statistics
        summary = {}  # reward_type -> count
        expired_ids = []

        for reward in stale_qs.iterator(chunk_size=1000):
            summary[reward.reward_type] = summary.get(reward.reward_type, 0) + 1
            expired_ids.append(str(reward.id))

        total = len(expired_ids)

        # Print summary to stdout (human-readable)
        self.stdout.write(self.style.NOTICE("=" * 50))
        self.stdout.write(self.style.NOTICE("STALE REWARDS AUDIT REPORT"))
        self.stdout.write(self.style.NOTICE("=" * 50))
        self.stdout.write(f"Cutoff date: {cutoff_date.isoformat()}")
        self.stdout.write(f"Dry run:     {dry_run}")
        self.stdout.write(f"Total found: {total}")
        self.stdout.write("")

        if not summary:
            self.stdout.write(self.style.SUCCESS("No stale rewards found."))
            return

        self.stdout.write("Breakdown by reward_type:")
        for reward_type, count in sorted(summary.items()):
            self.stdout.write(f"  {reward_type}: {count}")

        self.stdout.write("")

        # Log every expired reward ID at INFO level
        for reward_id in expired_ids:
            logger.info("Stale reward identified: id=%s", reward_id)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN complete. {total} rewards would be expired. "
                    "Run with --fix to apply changes."
                )
            )
            return

        # --fix path: update eligible records in a transaction
        self.stdout.write(self.style.WARNING(f"Applying expiration to {total} rewards..."))

        with transaction.atomic():
            update_qs = Reward.objects.filter(
                status=Reward.STATUS_CLAIMED,
                claimed_at__lt=cutoff_date,
            ).select_for_update()

            updated_count = update_qs.update(
                status=Reward.STATUS_EXPIRED,
                expires_at=timezone.now(),
            )

        self.stdout.write(
            self.style.SUCCESS(f"Successfully expired {updated_count} rewards.")
        )
        logger.info("Batch expiration complete: %d rewards updated.", updated_count)
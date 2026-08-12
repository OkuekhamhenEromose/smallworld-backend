from django.test import TestCase

# Create your tests here.
"""
Tests for Feature 2: Reward Approval Race Condition.
"""

import threading
from decimal import Decimal
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.db import connection

from apps.rewards.models import Reward
from apps.rewards.services import RewardApprovalService

User = get_user_model()


class RewardApprovalTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="rewarduser", email="reward@example.com", password="testpass"
        )
        self.reward = Reward.objects.create(
            user=self.user,
            status=Reward.STATUS_CLAIMED,
            amount=Decimal("100.00"),
            paystack_recipient_code="RCP_abc123",
            reward_type="signup_bonus",
        )

    def test_approve_success(self):
        """Happy path: approve a claimed reward."""
        result = RewardApprovalService.approve(str(self.reward.id))
        self.assertEqual(result["status"], 200)

        self.reward.refresh_from_db()
        self.assertEqual(self.reward.status, Reward.STATUS_APPROVED)
        self.assertTrue(self.reward.transfer_code.startswith("TRF_"))

    def test_approve_already_approved(self):
        """Double-approval attempt should be rejected."""
        RewardApprovalService.approve(str(self.reward.id))

        result = RewardApprovalService.approve(str(self.reward.id))
        self.assertEqual(result["status"], 400)
        self.assertIn("Not claimable", result["error"])

    def test_approve_race_condition(self):
        """
        Simulate concurrent approval requests.
        Without select_for_update, both threads could pass the status check
        and create two transfers. With select_for_update, one blocks until
        the other commits, then sees status='approved' and rejects.
        """
        results = []

        def approve():
            try:
                result = RewardApprovalService.approve(str(self.reward.id))
                results.append(result)
            except Exception as e:
                results.append({"error": str(e)})

        # Start two threads simultaneously
        t1 = threading.Thread(target=approve)
        t2 = threading.Thread(target=approve)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # One should succeed, one should fail (or both succeed if idempotent)
        success_count = sum(1 for r in results if r.get("status") == 200)
        fail_count = sum(1 for r in results if r.get("status") == 400)

        # With proper locking, exactly one succeeds
        self.assertEqual(success_count, 1, f"Expected 1 success, got: {results}")
        self.assertEqual(fail_count, 1, f"Expected 1 failure, got: {results}")

        # Verify only one transfer_code was created
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.status, Reward.STATUS_APPROVED)
        # transfer_code should be set exactly once (not concatenated or doubled)
        self.assertEqual(self.reward.transfer_code.count("TRF_"), 1)
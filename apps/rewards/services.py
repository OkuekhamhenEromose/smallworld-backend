"""
Business logic and external service integration for rewards.
"""

import logging
import uuid as uuid_lib
from django.db import transaction

from .models import Reward

logger = logging.getLogger(__name__)


class PaystackService:
    """
    Simulated Paystack integration.
    In production, this would make HTTP requests to Paystack API.
    """

    @staticmethod
    def initiate_transfer(*, amount: str, recipient: str, idempotency_key: str) -> dict:
        """
        Initiate a transfer to a recipient.

        idempotency_key: CRITICAL for external idempotency.
        If we retry the same transfer due to a network timeout,
        Paystack will return the same transfer_code instead of creating
        a new transfer. This prevents double payment even if our DB
        transaction rolled back and we retry the whole flow.
        """
        # Simulate external API call
        logger.info(
            "Paystack transfer: amount=%s recipient=%s idempotency=%s",
            amount,
            recipient,
            idempotency_key,
        )
        # In production: requests.post('https://api.paystack.co/transfer', ...)
        return {
            "transfer_code": f"TRF_{uuid_lib.uuid4().hex[:12].upper()}",
            "status": "success",
        }


class RewardApprovalService:
    """
    Encapsulates reward approval logic with concurrency safety.
    """

    @staticmethod
    def approve(reward_id: str) -> dict:
        """
        Approve a claimed reward and initiate Paystack transfer.

        Concurrency protection:
        1. select_for_update() locks the row until transaction commits.
        2. Transaction ensures DB state and external call are consistent.
           Note: The external Paystack call happens INSIDE the transaction.
           This is a trade-off: if Paystack succeeds but the DB commit fails,
           we have an orphaned transfer. We mitigate this with idempotency_key
           so a retry will return the same transfer_code, not create a new one.
        """
        with transaction.atomic():
            # select_for_update() acquires a row-level lock.
            # Other transactions trying to SELECT this row will BLOCK
            # until this transaction commits or rolls back.
            try:
                reward = (
                    Reward.objects.select_for_update()
                    .get(pk=reward_id)
                )
            except Reward.DoesNotExist:
                return {"error": "Reward not found", "status": 404}

            # State machine guard: only claimed rewards can be approved
            if reward.status != Reward.STATUS_CLAIMED:
                return {
                    "error": f"Not claimable. Current status: {reward.status}",
                    "status": 400,
                }

            # Generate idempotency key from reward ID + amount + recipient.
            # If this exact combination retries, Paystack returns the same result.
            idempotency_key = (
                f"reward-{reward_id}-{reward.amount}-{reward.paystack_recipient_code}"
            )

            result = PaystackService.initiate_transfer(
                amount=str(reward.amount),
                recipient=reward.paystack_recipient_code,
                idempotency_key=idempotency_key,
            )

            # Update state ONLY after external confirmation.
            # If Paystack failed, we would raise here and rollback.
            reward.status = Reward.STATUS_APPROVED
            reward.transfer_code = result["transfer_code"]
            reward.save(update_fields=["status", "transfer_code", "updated_at"])

        # Lock is released here when transaction commits.
        logger.info("Reward %s approved with transfer %s", reward_id, result["transfer_code"])
        return {"detail": "Approved", "transfer_code": result["transfer_code"], "status": 200}
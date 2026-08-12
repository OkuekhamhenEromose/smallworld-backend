"""
API views for rewards.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .services import RewardApprovalService


@api_view(["POST"])
@permission_classes([IsAdminUser])
def approve_reward(request, reward_id):
    """
    Admin endpoint to approve a reward.

    Security: Only admin users can approve.
    Concurrency: Protected by select_for_update in the service layer.
    """
    result = RewardApprovalService.approve(reward_id)

    status_code = result.pop("status", 200)
    return Response(result, status=status_code)
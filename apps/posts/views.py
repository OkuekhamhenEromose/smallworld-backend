"""
Post views placeholder.
Add post CRUD endpoints here if needed for the assessment.
"""
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def post_list(request):
    return Response({"detail": "Posts endpoint placeholder"})
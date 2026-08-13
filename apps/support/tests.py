from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import connection

from apps.support.models import SupportTicket

# Create your tests here.

User = get_user_model()

class SupportTicketIndexTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            username="operator", email="op@example.com", password="testpass"
        )
        for i in range(100):
            SupportTicket.objects.create(
                user=self.operator,
                status=SupportTicket.STATUS_OPEN,
                assigned_operator=self.operator,
                subject=f"Ticket {i}",
            )

    def test_query_uses_index(self):
        qs = SupportTicket.objects.filter(
            status="open",
            assigned_operator=self.operator,
        ).order_by("-created_at")[:20]

        with connection.cursor() as cursor:
            sql, params = qs.query.sql_with_params()
            cursor.execute(f"EXPLAIN {sql}", params)
            plan = "\n".join(row[0] for row in cursor.fetchall())

        self.assertNotIn("Seq Scan", plan, f"Sequential scan detected! Plan:\n{plan}")
        self.assertIn("Index", plan, f"Expected index usage. Plan:\n{plan}")

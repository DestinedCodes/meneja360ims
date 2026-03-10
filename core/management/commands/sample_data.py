from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from core.models import BusinessProfile, Client, Transaction, Expense
import random

class Command(BaseCommand):
    help = 'Create sample data for the dashboard'

    def handle(self, *args, **options):
        # Get or create business
        business, created = BusinessProfile.objects.get_or_create(
            name="CyberPoa Solutions",
            defaults={
                'owner_name': 'John Doe',
                'phone': '+1234567890',
                'email': 'john@cyberpoa.com',
                'location': '123 Tech Street, Silicon Valley'
            }
        )

        # Create sample clients
        clients_data = [
            {'full_name': 'Alice Johnson', 'phone': '+1987654321', 'client_type': 'regular'},
            {'full_name': 'Bob Smith', 'phone': '+1123456789', 'client_type': 'corporate'},
            {'full_name': 'Carol Williams', 'phone': '+1567890123', 'client_type': 'walkin'},
            {'full_name': 'David Brown', 'phone': '+1456789012', 'client_type': 'regular'},
            {'full_name': 'Eva Davis', 'phone': '+1345678901', 'client_type': 'corporate'},
        ]

        clients = []
        for client_data in clients_data:
            client, created = Client.objects.get_or_create(
                business=business,
                full_name=client_data['full_name'],
                defaults={
                    'phone_number': client_data['phone'],
                    'client_type': client_data['client_type'],
                    'total_spending': 0,
                    'outstanding_balance': 0,
                }
            )
            clients.append(client)

        # Create sample transactions for the last 12 months
        services = ['Web Development', 'Mobile App', 'Consulting', 'SEO Optimization', 'UI/UX Design']
        today = timezone.now()

        for i in range(50):  # Create 50 transactions
            # Random date within the last year
            days_ago = random.randint(0, 365)
            transaction_date = today - timedelta(days=days_ago)

            client = random.choice(clients) if random.random() > 0.3 else None  # 70% have clients
            service = random.choice(services)
            unit_price = random.randint(50, 500)
            quantity = random.randint(1, 10)
            total_amount = unit_price * quantity

            # Random payment status
            payment_status = random.choice(['paid', 'partial', 'unpaid'])
            if payment_status == 'paid':
                amount_paid = total_amount
            elif payment_status == 'partial':
                amount_paid = random.randint(1, total_amount - 1)
            else:
                amount_paid = 0

            Transaction.objects.get_or_create(
                business=business,
                date=transaction_date,
                client=client,
                service_name=service,
                defaults={
                    'unit_price': unit_price,
                    'quantity': quantity,
                    'total_amount': total_amount,
                    'amount_paid': amount_paid,
                    'status': payment_status,
                }
            )

        # Create sample expenses for the last 12 months
        expense_categories = ['rent', 'electricity', 'internet', 'supplies', 'salary', 'maintenance']
        expense_descriptions = {
            'rent': 'Monthly office rent',
            'electricity': 'Electricity bill',
            'internet': 'Internet service',
            'supplies': 'Office supplies',
            'salary': 'Employee salaries',
            'maintenance': 'Equipment maintenance',
        }

        for i in range(30):  # Create 30 expenses
            days_ago = random.randint(0, 365)
            expense_date = today - timedelta(days=days_ago)

            category = random.choice(expense_categories)
            amount = random.randint(100, 2000)

            Expense.objects.get_or_create(
                business=business,
                date=expense_date,
                category=category,
                defaults={
                    'description': expense_descriptions.get(category, f'{category} expense'),
                    'amount': amount,
                }
            )

        self.stdout.write(
            self.style.SUCCESS('Successfully created sample data for the dashboard!')
        )
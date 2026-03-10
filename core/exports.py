from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.template.loader import get_template
from django.db.models import Sum
from django.utils import timezone
from datetime import datetime, timedelta
from .models import BusinessProfile, Client, Transaction, Expense
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch


@login_required
def export_daily_report_pdf(request):
    """Export daily report to PDF"""
    report_date = request.GET.get('date', timezone.now().date())
    if isinstance(report_date, str):
        report_date = datetime.strptime(report_date, '%Y-%m-%d').date()

    business = BusinessProfile.objects.first()

    # Get data
    revenue = Transaction.objects.filter(
        business=business, date__date=report_date
    ).aggregate(total=Sum('amount_paid'))['total'] or 0

    expenses = Expense.objects.filter(
        business=business, date__date=report_date
    ).aggregate(total=Sum('amount'))['total'] or 0

    transactions = Transaction.objects.filter(
        business=business, date__date=report_date
    ).select_related('client').order_by('-date')

    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
    )
    story.append(Paragraph(f"Daily Report - {business.name}", title_style))
    story.append(Paragraph(f"Date: {report_date.strftime('%B %d, %Y')}", styles['Normal']))
    story.append(Spacer(1, 12))

    # Summary
    story.append(Paragraph("Summary", styles['Heading2']))
    summary_data = [
        ['Total Revenue', f"${revenue:.2f}"],
        ['Total Expenses', f"${expenses:.2f}"],
        ['Net Profit', f"${(revenue - expenses):.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[2*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 20))

    # Transactions
    if transactions:
        story.append(Paragraph("Transactions", styles['Heading2']))
        transaction_data = [['Date', 'Client', 'Service', 'Amount Paid', 'Status']]
        for t in transactions:
            client_name = t.client.full_name if t.client else 'Walk-in'
            transaction_data.append([
                t.date.strftime('%H:%M'),
                client_name,
                t.service_name,
                f"${t.amount_paid:.2f}",
                t.get_status_display()
            ])

        transaction_table = Table(transaction_data, colWidths=[1*inch, 1.5*inch, 2*inch, 1*inch, 1*inch])
        transaction_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
        ]))
        story.append(transaction_table)

    doc.build(story)

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="daily_report_{report_date}.pdf"'
    return response


@login_required
def export_monthly_report_pdf(request):
    """Export monthly report to PDF"""
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))

    business = BusinessProfile.objects.first()

    # Get data
    start_date = datetime(year, month, 1).date()
    end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    revenue = Transaction.objects.filter(
        business=business, date__date__range=(start_date, end_date)
    ).aggregate(total=Sum('amount_paid'))['total'] or 0

    expenses = Expense.objects.filter(
        business=business, date__date__range=(start_date, end_date)
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
    )
    story.append(Paragraph(f"Monthly Report - {business.name}", title_style))
    story.append(Paragraph(f"Period: {start_date.strftime('%B %Y')}", styles['Normal']))
    story.append(Spacer(1, 12))

    # Summary
    story.append(Paragraph("Summary", styles['Heading2']))
    summary_data = [
        ['Total Revenue', f"${revenue:.2f}"],
        ['Total Expenses', f"${expenses:.2f}"],
        ['Net Profit', f"${(revenue - expenses):.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[2*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 20))

    doc.build(story)

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="monthly_report_{year}_{month}.pdf"'
    return response


@login_required
def export_yearly_report_pdf(request):
    """Export yearly report to PDF"""
    year = int(request.GET.get('year', timezone.now().year))

    business = BusinessProfile.objects.first()

    # Get data
    yearly_revenue = Transaction.objects.filter(
        business=business, date__year=year
    ).aggregate(total=Sum('amount_paid'))['total'] or 0

    yearly_expenses = Expense.objects.filter(
        business=business, date__year=year
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Monthly breakdown
    monthly_data = []
    for m in range(1, 13):
        month_start = datetime(year, m, 1).date()
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        revenue = Transaction.objects.filter(
            business=business, date__date__range=(month_start, month_end)
        ).aggregate(total=Sum('amount_paid'))['total'] or 0

        expenses = Expense.objects.filter(
            business=business, date__date__range=(month_start, month_end)
        ).aggregate(total=Sum('amount'))['total'] or 0

        monthly_data.append([
            month_start.strftime('%B'),
            f"${revenue:.2f}",
            f"${expenses:.2f}",
            f"${(revenue - expenses):.2f}",
        ])

    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
    )
    story.append(Paragraph(f"Yearly Report - {business.name}", title_style))
    story.append(Paragraph(f"Year: {year}", styles['Normal']))
    story.append(Spacer(1, 12))

    # Summary
    story.append(Paragraph("Annual Summary", styles['Heading2']))
    summary_data = [
        ['Total Revenue', f"${yearly_revenue:.2f}"],
        ['Total Expenses', f"${yearly_expenses:.2f}"],
        ['Net Profit', f"${(yearly_revenue - yearly_expenses):.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[2*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 20))

    # Monthly Breakdown
    story.append(Paragraph("Monthly Breakdown", styles['Heading2']))
    monthly_headers = [['Month', 'Revenue', 'Expenses', 'Profit']]
    monthly_table_data = monthly_headers + monthly_data

    monthly_table = Table(monthly_table_data, colWidths=[1.5*inch, 1.2*inch, 1.2*inch, 1.2*inch])
    monthly_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(monthly_table)

    doc.build(story)

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="yearly_report_{year}.pdf"'
    return response


@login_required
def export_client_statement_pdf(request, client_id):
    """Export client statement to PDF"""
    client = Client.objects.get(id=client_id)
    business = client.business

    # Get all transactions for this client
    transactions = Transaction.objects.filter(
        client=client
    ).order_by('-date')

    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
    )
    story.append(Paragraph(f"Client Statement - {business.name}", title_style))
    story.append(Paragraph(f"Client: {client.full_name}", styles['Normal']))
    story.append(Paragraph(f"Phone: {client.phone_number}", styles['Normal']))
    story.append(Paragraph(f"Generated: {timezone.now().strftime('%B %d, %Y')}", styles['Normal']))
    story.append(Spacer(1, 12))

    # Client Summary
    story.append(Paragraph("Account Summary", styles['Heading2']))
    summary_data = [
        ['Total Spending', f"${client.total_spending:.2f}"],
        ['Outstanding Balance', f"${client.outstanding_balance:.2f}"],
        ['Client Type', client.get_client_type_display()],
    ]
    summary_table = Table(summary_data, colWidths=[2*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 20))

    # Transaction History
    if transactions:
        story.append(Paragraph("Transaction History", styles['Heading2']))
        transaction_data = [['Date', 'Service', 'Total Amount', 'Amount Paid', 'Balance', 'Status']]
        for t in transactions:
            transaction_data.append([
                t.date.strftime('%Y-%m-%d'),
                t.service_name,
                f"${t.total_amount:.2f}",
                f"${t.amount_paid:.2f}",
                f"${t.balance:.2f}",
                t.get_status_display()
            ])

        transaction_table = Table(transaction_data, colWidths=[1*inch, 2*inch, 1*inch, 1*inch, 1*inch, 1*inch])
        transaction_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        story.append(transaction_table)

    doc.build(story)

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="client_statement_{client.full_name.replace(' ', '_')}.pdf"'
    return response


@login_required
def print_revenue_report(request):
    """Print revenue report"""
    # This would typically open a print dialog
    # For now, we'll redirect to the report with print styles
    report_type = request.GET.get('type', 'daily')
    if report_type == 'daily':
        return redirect('daily_report')
    elif report_type == 'monthly':
        return redirect('monthly_report')
    elif report_type == 'yearly':
        return redirect('yearly_report')
    else:
        return redirect('report_index')
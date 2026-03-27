import io
import json
from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, Sum
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image as ReportImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .currency import format_ksh
from .expense_utils import combined_expense_total, expense_breakdown_by_category, general_expenses_qs
from .models import Client, SupplyExpense, Transaction
from .permissions import AdminRequiredMixin, ReportsRequiredMixin, can_backup_restore, can_view_reports
from .tenancy import get_user_business


SYSTEM_NAME = "Meneja360°"


def _parse_date(value, fallback):
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return fallback


def _parse_month(value, fallback):
    try:
        year, month = map(int, str(value).split("-"))
        return date(year, month, 1)
    except (TypeError, ValueError):
        return fallback.replace(day=1)


def _month_end(month_start):
    return (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def _build_report_entries(business, start_date, end_date):
    transactions = (
        Transaction.objects.filter(business=business, date__date__range=(start_date, end_date))
        .select_related("client")
        .order_by("-date")
    )
    expenses = general_expenses_qs(business).filter(date__date__range=(start_date, end_date)).order_by("-date")
    supply_expenses = SupplyExpense.objects.filter(
        business=business,
        date__date__range=(start_date, end_date),
    ).order_by("-date")

    expense_labels = dict(getattr(expenses.model, "CATEGORY_CHOICES", []))
    rows = []

    for transaction in transactions:
        client_name = transaction.client.full_name if transaction.client else "Walk-in"
        rows.append({
            "date": transaction.date,
            "description": f"{transaction.service_name} - {client_name}",
            "revenue": transaction.amount_paid,
            "expense": 0,
            "entry_type": "Revenue",
        })

    for expense in expenses:
        category_label = expense_labels.get(expense.category, str(expense.category).title())
        description = expense.description or category_label
        rows.append({
            "date": expense.date,
            "description": f"{category_label} - {description}",
            "revenue": 0,
            "expense": expense.amount,
            "entry_type": "Expense",
        })

    for supply in supply_expenses:
        supplier_bits = [bit for bit in [supply.supplier_name, supply.supplier_contact] if bit]
        supplier_text = " | ".join(supplier_bits)
        base_description = supply.description or "Supplies purchase"
        full_description = f"Supplies - {base_description}"
        if supplier_text:
            full_description = f"{full_description} ({supplier_text})"
        rows.append({
            "date": supply.date,
            "description": full_description,
            "revenue": 0,
            "expense": supply.amount,
            "entry_type": "Supply",
        })

    rows.sort(key=lambda item: item["date"], reverse=True)
    return rows


def _build_daily_trend(business, report_date):
    labels = []
    values = []
    for hour in range(24):
        start_dt = timezone.make_aware(datetime.combine(report_date, time(hour=hour, minute=0)))
        end_dt = start_dt + timedelta(hours=1)
        amount = (
            Transaction.objects.filter(
                business=business,
                date__gte=start_dt,
                date__lt=end_dt,
            ).aggregate(total=Sum("amount_paid"))["total"] or 0
        )
        labels.append(start_dt.strftime("%H:%M"))
        values.append(float(amount))
    return {"labels": labels, "datasets": [{"label": "Revenue", "data": values}]}


def _build_monthly_trend(business, month_start, month_end):
    labels = []
    values = []
    current_day = month_start
    while current_day <= month_end:
        amount = (
            Transaction.objects.filter(
                business=business,
                date__date=current_day,
            ).aggregate(total=Sum("amount_paid"))["total"] or 0
        )
        labels.append(current_day.strftime("%d %b"))
        values.append(float(amount))
        current_day += timedelta(days=1)
    return {"labels": labels, "datasets": [{"label": "Revenue", "data": values}]}


def _build_yearly_trend(business, year):
    labels = []
    values = []
    for month_number in range(1, 13):
        start_date = date(year, month_number, 1)
        end_date = _month_end(start_date)
        revenue = (
            Transaction.objects.filter(
                business=business,
                date__date__range=(start_date, end_date),
            ).aggregate(total=Sum("amount_paid"))["total"] or 0
        )
        expenses = combined_expense_total(
            business,
            date__date__range=(start_date, end_date),
        )
        labels.append(start_date.strftime("%b"))
        values.append(float(revenue))
    return {"labels": labels, "datasets": [{"label": "Revenue", "data": values}]}


def _branding_details(business):
    contact_lines = [value for value in [business.phone, business.email, business.location] if value]
    return {
        "logo_url": business.logo.url if getattr(business, "logo", None) else None,
        "contact_lines": contact_lines,
        "business_name": business.name,
    }


def _build_report_context(
    *,
    business,
    report_type,
    report_period_label,
    start_date,
    end_date,
    filter_mode,
    filter_value,
    previous_value,
    next_value,
    export_url_name,
    line_chart_data,
    table_rows,
):
    revenue = (
        Transaction.objects.filter(
            business=business,
            date__date__range=(start_date, end_date),
        ).aggregate(total=Sum("amount_paid"))["total"] or 0
    )
    expenses = combined_expense_total(
        business,
        date__date__range=(start_date, end_date),
    )
    net_profit = revenue - expenses
    expense_breakdown = expense_breakdown_by_category(
        business,
        date__date__range=(start_date, end_date),
    )
    generated_at = timezone.localtime()

    return {
        "business": business,
        "branding": _branding_details(business),
        "report_type": report_type,
        "report_period_label": report_period_label,
        "report_period_start": start_date,
        "report_period_end": end_date,
        "revenue": revenue,
        "expenses": expenses,
        "net_profit": net_profit,
        "table_rows": table_rows,
        "filter_mode": filter_mode,
        "filter_value": filter_value,
        "previous_value": previous_value,
        "next_value": next_value,
        "export_url_name": export_url_name,
        "generated_at": generated_at,
        "system_name": SYSTEM_NAME,
        "bar_chart_data": json.dumps({
            "labels": ["Revenue", "Expenses"],
            "datasets": [{
                "label": report_type,
                "data": [float(revenue), float(expenses)],
                "backgroundColor": ["#1f9d55", "#d64545"],
                "borderRadius": 10,
            }],
        }),
        "line_chart_data": json.dumps(line_chart_data),
        "expense_chart_data": json.dumps({
            "labels": [row["category"] for row in expense_breakdown] or ["No expenses"],
            "datasets": [{
                "data": [row["total"] for row in expense_breakdown] or [1],
                "backgroundColor": [
                    "#d64545",
                    "#f59e0b",
                    "#0f766e",
                    "#2563eb",
                    "#7c3aed",
                    "#475569",
                ],
            }],
        }),
        "expense_breakdown": expense_breakdown,
        "signature_label": "Authorised Signature",
    }


def _build_pdf_response(filename, report_type, report_period_label, context):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=32,
        leftMargin=32,
        topMargin=28,
        bottomMargin=28,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#12263A"),
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
    )
    muted_style = ParagraphStyle(
        "ReportMuted",
        parent=body_style,
        textColor=colors.HexColor("#64748B"),
    )
    story = []

    logo_cell = ""
    if context["branding"]["logo_url"]:
        try:
            logo_path = context["business"].logo.path
            logo_cell = ReportImage(logo_path, width=0.9 * inch, height=0.9 * inch)
        except Exception:
            logo_cell = ""

    business_name = context["branding"]["business_name"]
    contact_html = "<br/>".join(context["branding"]["contact_lines"]) or "No contact details set"
    header_info = [
        Paragraph(business_name, title_style),
        Paragraph(f"<b>{report_type}</b>", body_style),
        Paragraph(report_period_label, body_style),
        Paragraph(contact_html, muted_style),
    ]
    header_table = Table([[logo_cell, header_info]], colWidths=[1.1 * inch, 5.8 * inch])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 14))

    summary_data = [
        ["Total Revenue", format_ksh(context["revenue"])],
        ["Total Expenses", format_ksh(context["expenses"])],
        ["Net Profit", format_ksh(context["net_profit"])],
    ]
    summary_table = Table(summary_data, colWidths=[2.4 * inch, 2.2 * inch])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 2), (1, 2), "Helvetica-Bold"),
        ("TEXTCOLOR", (1, 0), (1, 0), colors.HexColor("#1f9d55")),
        ("TEXTCOLOR", (1, 1), (1, 1), colors.HexColor("#d64545")),
        ("TEXTCOLOR", (1, 2), (1, 2), colors.HexColor("#12263A")),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 14))

    table_data = [["Date", "Description", "Revenue", "Expenses"]]
    for row in context["table_rows"]:
        table_data.append([
            timezone.localtime(row["date"]).strftime("%Y-%m-%d %H:%M") if timezone.is_aware(row["date"]) else row["date"].strftime("%Y-%m-%d %H:%M"),
            row["description"],
            format_ksh(row["revenue"]) if row["revenue"] else "-",
            format_ksh(row["expense"]) if row["expense"] else "-",
        ])
    if len(table_data) == 1:
        table_data.append(["-", "No transactions or expenses recorded for this period.", "-", "-"])

    detail_table = Table(table_data, colWidths=[1.3 * inch, 3.2 * inch, 1.15 * inch, 1.15 * inch], repeatRows=1)
    detail_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#12263A")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(detail_table)
    story.append(Spacer(1, 14))

    footer_text = (
        f"Generated: {timezone.localtime(context['generated_at']).strftime('%d %b %Y %H:%M')}<br/>"
        f"System: {context['system_name']}<br/>"
        f"Signature: ______________________________"
    )
    story.append(Paragraph(footer_text, muted_style))

    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class ReportIndexView(LoginRequiredMixin, ReportsRequiredMixin, TemplateView):
    template_name = "core/reports.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        business = get_user_business(self.request.user)
        today_revenue = (
            Transaction.objects.filter(
                business=business,
                date__date=today,
            ).aggregate(total=Sum("amount_paid"))["total"] or 0
        )
        today_expenses = combined_expense_total(
            business,
            date__date=today,
        )
        context.update({
            "business": business,
            "branding": _branding_details(business),
            "today_revenue": today_revenue,
            "today_expenses": today_expenses,
            "net_profit": today_revenue - today_expenses,
            "today_filter": today.strftime("%Y-%m-%d"),
            "month_filter": today.strftime("%Y-%m"),
            "year_filter": today.year,
        })
        return context


class DailyReportView(LoginRequiredMixin, ReportsRequiredMixin, TemplateView):
    template_name = "core/daily_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        report_date = _parse_date(self.request.GET.get("date"), timezone.localdate())
        business = get_user_business(self.request.user)
        table_rows = _build_report_entries(business, report_date, report_date)
        line_chart = _build_daily_trend(business, report_date)
        context.update(_build_report_context(
            business=business,
            report_type="Daily Report",
            report_period_label=report_date.strftime("%A, %d %B %Y"),
            start_date=report_date,
            end_date=report_date,
            filter_mode="daily",
            filter_value=report_date.strftime("%Y-%m-%d"),
            previous_value=(report_date - timedelta(days=1)).strftime("%Y-%m-%d"),
            next_value=(report_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            export_url_name="export_daily_report_pdf",
            line_chart_data=line_chart,
            table_rows=table_rows,
        ))
        return context


class MonthlyReportView(LoginRequiredMixin, ReportsRequiredMixin, TemplateView):
    template_name = "core/monthly_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        month_start = _parse_month(self.request.GET.get("month"), timezone.localdate().replace(day=1))
        month_end = _month_end(month_start)
        business = get_user_business(self.request.user)
        table_rows = _build_report_entries(business, month_start, month_end)
        line_chart = _build_monthly_trend(business, month_start, month_end)
        previous_month = (month_start - timedelta(days=1)).replace(day=1)
        next_month = (month_end + timedelta(days=1)).replace(day=1)
        context.update(_build_report_context(
            business=business,
            report_type="Monthly Report",
            report_period_label=month_start.strftime("%B %Y"),
            start_date=month_start,
            end_date=month_end,
            filter_mode="monthly",
            filter_value=month_start.strftime("%Y-%m"),
            previous_value=previous_month.strftime("%Y-%m"),
            next_value=next_month.strftime("%Y-%m"),
            export_url_name="export_monthly_report_pdf",
            line_chart_data=line_chart,
            table_rows=table_rows,
        ))
        return context


class YearlyReportView(LoginRequiredMixin, ReportsRequiredMixin, TemplateView):
    template_name = "core/yearly_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year = int(self.request.GET.get("year", timezone.localdate().year))
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        business = get_user_business(self.request.user)
        line_chart = _build_yearly_trend(business, year)
        context.update(_build_report_context(
            business=business,
            report_type="Yearly Report",
            report_period_label=str(year),
            start_date=start_date,
            end_date=end_date,
            filter_mode="yearly",
            filter_value=year,
            previous_value=year - 1,
            next_value=year + 1,
            export_url_name="export_yearly_report_pdf",
            line_chart_data=line_chart,
            table_rows=_build_report_entries(business, start_date, end_date),
        ))
        return context


class CustomReportView(LoginRequiredMixin, ReportsRequiredMixin, TemplateView):
    template_name = "core/custom_report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        start_date_str = self.request.GET.get("start")
        end_date_str = self.request.GET.get("end")
        business = get_user_business(self.request.user)

        if start_date_str and end_date_str:
            start_date = _parse_date(start_date_str, timezone.localdate().replace(day=1))
            end_date = _parse_date(end_date_str, timezone.localdate())
            revenue = (
                Transaction.objects.filter(
                    business=business,
                    date__date__range=(start_date, end_date),
                ).aggregate(total=Sum("amount_paid"))["total"] or 0
            )
            expenses = combined_expense_total(
                business,
                date__date__range=(start_date, end_date),
            )
            total_transactions = Transaction.objects.filter(
                business=business,
                date__date__range=(start_date, end_date),
            ).count()
            daily_data = []
            current_date = start_date
            daily_revenue_data = {"labels": [], "data": []}
            while current_date <= end_date:
                day_revenue = (
                    Transaction.objects.filter(
                        business=business,
                        date__date=current_date,
                    ).aggregate(total=Sum("amount_paid"))["total"] or 0
                )
                day_expenses = combined_expense_total(
                    business,
                    date__date=current_date,
                )
                day_transactions = Transaction.objects.filter(
                    business=business,
                    date__date=current_date,
                ).count()
                daily_data.append({
                    "date": current_date,
                    "revenue": day_revenue,
                    "expenses": day_expenses,
                    "profit": day_revenue - day_expenses,
                    "transactions": day_transactions,
                })
                daily_revenue_data["labels"].append(current_date.strftime("%m/%d"))
                daily_revenue_data["data"].append(float(day_revenue))
                current_date += timedelta(days=1)

            top_clients = Client.objects.filter(
                business=business,
                transactions__date__date__range=(start_date, end_date),
            ).annotate(
                total_spent=Sum("transactions__amount_paid"),
                transaction_count=Count("transactions"),
                avg_transaction=Avg("transactions__amount_paid"),
            ).order_by("-total_spent")[:10]

            expense_categories = expense_breakdown_by_category(
                business,
                date__date__range=(start_date, end_date),
            )

            context.update({
                "business": business,
                "start_date": start_date,
                "end_date": end_date,
                "days_count": (end_date - start_date).days + 1,
                "revenue": revenue,
                "expenses": expenses,
                "net_profit": revenue - expenses,
                "total_transactions": total_transactions,
                "daily_data": daily_data,
                "daily_revenue": json.dumps(daily_revenue_data),
                "top_clients": top_clients,
                "expense_categories": expense_categories,
            })
        else:
            today = timezone.localdate()
            context.update({
                "business": business,
                "start_date": today.replace(day=1),
                "end_date": today,
            })
        return context


class BackupView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    template_name = "core/backup.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["business"] = get_user_business(self.request.user)
        return context

    def dispatch(self, request, *args, **kwargs):
        if not can_backup_restore(request.user):
            messages.error(request, "Only the business owner can create backups.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)


class RestoreView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    template_name = "core/restore.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["business"] = get_user_business(self.request.user)
        return context

    def dispatch(self, request, *args, **kwargs):
        if not can_backup_restore(request.user):
            messages.error(request, "Only the business owner can restore backups.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)


def export_daily_report_pdf(request):
    if not request.user.is_authenticated or not can_view_reports(request.user):
        raise PermissionDenied("You do not have permission to export reports.")

    report_date = _parse_date(request.GET.get("date"), timezone.localdate())
    business = get_user_business(request.user)
    context = _build_report_context(
        business=business,
        report_type="Daily Report",
        report_period_label=report_date.strftime("%A, %d %B %Y"),
        start_date=report_date,
        end_date=report_date,
        filter_mode="daily",
        filter_value=report_date.strftime("%Y-%m-%d"),
        previous_value="",
        next_value="",
        export_url_name="export_daily_report_pdf",
        line_chart_data=_build_daily_trend(business, report_date),
        table_rows=_build_report_entries(business, report_date, report_date),
    )
    return _build_pdf_response(
        f"daily_report_{report_date.isoformat()}.pdf",
        "Daily Report",
        context["report_period_label"],
        context,
    )


def export_monthly_report_pdf(request):
    if not request.user.is_authenticated or not can_view_reports(request.user):
        raise PermissionDenied("You do not have permission to export reports.")

    month_start = _parse_month(request.GET.get("month"), timezone.localdate().replace(day=1))
    month_end = _month_end(month_start)
    business = get_user_business(request.user)
    context = _build_report_context(
        business=business,
        report_type="Monthly Report",
        report_period_label=month_start.strftime("%B %Y"),
        start_date=month_start,
        end_date=month_end,
        filter_mode="monthly",
        filter_value=month_start.strftime("%Y-%m"),
        previous_value="",
        next_value="",
        export_url_name="export_monthly_report_pdf",
        line_chart_data=_build_monthly_trend(business, month_start, month_end),
        table_rows=_build_report_entries(business, month_start, month_end),
    )
    return _build_pdf_response(
        f"monthly_report_{month_start.strftime('%Y_%m')}.pdf",
        "Monthly Report",
        context["report_period_label"],
        context,
    )


def export_yearly_report_pdf(request):
    if not request.user.is_authenticated or not can_view_reports(request.user):
        raise PermissionDenied("You do not have permission to export reports.")

    year = int(request.GET.get("year", timezone.localdate().year))
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)
    business = get_user_business(request.user)
    line_chart = _build_yearly_trend(business, year)
    context = _build_report_context(
        business=business,
        report_type="Yearly Report",
        report_period_label=str(year),
        start_date=start_date,
        end_date=end_date,
        filter_mode="yearly",
        filter_value=year,
        previous_value="",
        next_value="",
        export_url_name="export_yearly_report_pdf",
        line_chart_data=line_chart,
        table_rows=_build_report_entries(business, start_date, end_date),
    )
    return _build_pdf_response(
        f"yearly_report_{year}.pdf",
        "Yearly Report",
        context["report_period_label"],
        context,
    )


def export_custom_report_pdf(request):
    if not request.user.is_authenticated or not can_view_reports(request.user):
        raise PermissionDenied("You do not have permission to export reports.")

    start_date_str = request.GET.get("start")
    end_date_str = request.GET.get("end")
    if not start_date_str or not end_date_str:
        return HttpResponse("Date range required", status=400)

    start_date = _parse_date(start_date_str, timezone.localdate().replace(day=1))
    end_date = _parse_date(end_date_str, timezone.localdate())
    business = get_user_business(request.user)
    context = _build_report_context(
        business=business,
        report_type="Custom Report",
        report_period_label=f"{start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}",
        start_date=start_date,
        end_date=end_date,
        filter_mode="custom",
        filter_value="",
        previous_value="",
        next_value="",
        export_url_name="export_custom_report_pdf",
        line_chart_data=_build_monthly_trend(business, start_date, end_date),
        table_rows=_build_report_entries(business, start_date, end_date),
    )
    return _build_pdf_response(
        f"custom_report_{start_date.isoformat()}_{end_date.isoformat()}.pdf",
        "Custom Report",
        context["report_period_label"],
        context,
    )


report_index = ReportIndexView.as_view()
daily_report = DailyReportView.as_view()
monthly_report = MonthlyReportView.as_view()
yearly_report = YearlyReportView.as_view()
custom_report = CustomReportView.as_view()
backup = BackupView.as_view()
restore = RestoreView.as_view()

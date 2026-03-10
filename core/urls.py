from django.urls import path
from . import views
from .reporting import (
    ReportIndexView, DailyReportView, MonthlyReportView,
    YearlyReportView, CustomReportView, BackupView, RestoreView,
    export_daily_report_pdf, export_monthly_report_pdf,
    export_yearly_report_pdf, export_custom_report_pdf
)

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('business/', views.BusinessListView.as_view(), name='business_list'),
    path('business/add/', views.BusinessCreateView.as_view(), name='business_add'),
    path('business/<int:pk>/edit/', views.BusinessUpdateView.as_view(), name='business_edit'),
    path('clients/', views.ClientListView.as_view(), name='client_list'),
    path('clients/add/', views.ClientCreateView.as_view(), name='client_add'),
    path('clients/<int:pk>/edit/', views.ClientUpdateView.as_view(), name='client_edit'),
    path('transactions/', views.TransactionListView.as_view(), name='transaction_list'),
    path('transactions/add/', views.TransactionCreateView.as_view(), name='transaction_add'),
    path('transactions/<int:pk>/edit/', views.TransactionUpdateView.as_view(), name='transaction_edit'),
    path('expenses/', views.ExpenseListView.as_view(), name='expense_list'),
    path('expenses/add/', views.ExpenseCreateView.as_view(), name='expense_add'),
    path('expenses/<int:pk>/edit/', views.ExpenseUpdateView.as_view(), name='expense_edit'),
    # reporting and backup
    path('reports/', ReportIndexView.as_view(), name='report_index'),
    path('reports/daily/', DailyReportView.as_view(), name='daily_report'),
    path('reports/monthly/', MonthlyReportView.as_view(), name='monthly_report'),
    path('reports/yearly/', YearlyReportView.as_view(), name='yearly_report'),
    path('reports/custom/', CustomReportView.as_view(), name='custom_report'),
    path('backup/', BackupView.as_view(), name='backup'),
    path('restore/', RestoreView.as_view(), name='restore'),
    # export functions
    path('export/daily/pdf/', export_daily_report_pdf, name='export_daily_report_pdf'),
    path('export/monthly/pdf/', export_monthly_report_pdf, name='export_monthly_report_pdf'),
    path('export/yearly/pdf/', export_yearly_report_pdf, name='export_yearly_report_pdf'),
    path('export/custom/pdf/', export_custom_report_pdf, name='export_custom_report_pdf'),
    # authentication
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
]

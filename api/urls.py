from django.urls import path
from . import views

urlpatterns = [
    path('health', views.health_check, name='health_check'),
    path('api/v1/payouts', views.create_payout, name='create_payout'),
    path('api/v1/merchants/<uuid:merchant_id>/ledger', views.list_ledger_entries, name='list_ledger_entries'),
]

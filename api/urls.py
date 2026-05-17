from django.urls import path
from . import views
from . import auth_views

urlpatterns = [
    path('health', views.health_check, name='health_check'),
    path('api/auth/register', auth_views.register, name='register'),
    path('api/auth/login', auth_views.login_view, name='login'),
    path('api/v1/payouts', views.create_payout, name='create_payout'),
    path('api/v1/merchants/<uuid:merchant_id>/ledger', views.list_ledger_entries, name='list_ledger_entries'),
]

from django.contrib import admin
from .models import Merchant, Payout, Ledger, IdempotencyKey, OutboxEvent

@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'email', 'created_at')
    search_fields = ('name', 'email')

@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ('id', 'merchant', 'amount_paise', 'status', 'retry_count', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'merchant__name', 'bank_account_id')

@admin.register(Ledger)
class LedgerAdmin(admin.ModelAdmin):
    list_display = ('id', 'merchant', 'entry_type', 'amount_paise', 'created_at')
    list_filter = ('entry_type', 'created_at')
    search_fields = ('merchant__name',)

@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ('key', 'status', 'created_at')
    list_filter = ('status', 'created_at')

@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'event_type', 'status', 'created_at', 'processed_at')
    list_filter = ('status', 'event_type', 'created_at')

from django.contrib import admin

from .models import AuditEvent, Contract, LoanApplication, SignatureEvidence


@admin.register(LoanApplication)
class LoanApplicationAdmin(admin.ModelAdmin):
    list_display = ("reference", "full_name", "requested_amount", "status", "created_at")
    search_fields = ("reference", "full_name", "email")
    list_filter = ("status", "is_demo")
    readonly_fields = ("submitted_ip_hash", "user_agent_hash")


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("application", "total_repayment", "apr_percent", "status", "created_at")
    readonly_fields = ("draft_document_hash", "final_document_hash")


admin.site.register(SignatureEvidence)
admin.site.register(AuditEvent)

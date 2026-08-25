from django.urls import path

from . import views


urlpatterns = [
    path("", views.home, name="home"),
    path("apply/", views.apply, name="apply"),
    path("apply/received/", views.application_success, name="application_success"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path("staff/login/", views.staff_login, name="staff_login"),
    path("staff/mfa/setup/", views.staff_mfa_setup, name="staff_mfa_setup"),
    path("staff/mfa/verify/", views.staff_mfa_verify, name="staff_mfa_verify"),
    path("staff/mfa/recovery-codes/", views.staff_recovery_codes, name="staff_recovery_codes"),
    path("staff/logout/", views.staff_logout, name="staff_logout"),
    path("staff/", views.staff_dashboard, name="staff_dashboard"),
    path("staff/applications/", views.staff_applications, name="staff_applications"),
    path("staff/applications/<uuid:application_id>/", views.staff_application_detail, name="staff_application_detail"),
    path("staff/applications/<uuid:application_id>/contract/new/", views.staff_contract_create, name="staff_contract_create"),
    path("staff/contracts/<uuid:contract_id>/draft.pdf", views.staff_contract_pdf, name="staff_contract_pdf"),
    path("staff/contracts/<uuid:contract_id>/signed.pdf", lambda r, contract_id: views.staff_contract_pdf(r, contract_id, final=True), name="staff_contract_final_pdf"),
    path("staff/contracts/<uuid:contract_id>/send/", views.staff_contract_send, name="staff_contract_send"),
    path("sign/<str:token>/", views.sign_contract, name="sign_contract"),
    path("sign/<str:token>/agreement.pdf", views.signer_contract_pdf, name="signer_contract_pdf"),
    path("sign/<str:token>/signed-agreement.pdf", lambda r, token: views.signer_contract_pdf(r, token, final=True), name="signer_final_pdf"),
]

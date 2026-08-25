from django.conf import settings


def portal_context(request):
    return {
        "brand_name": settings.PUBLIC_BRAND_NAME,
        "business_legal_name": settings.BUSINESS_LEGAL_NAME,
        "business_address": settings.BUSINESS_ADDRESS,
        "business_registration_number": settings.BUSINESS_REGISTRATION_NUMBER,
        "authorization_reference": settings.LENDER_AUTHORIZATION_REFERENCE,
        "business_contact_email": settings.BUSINESS_CONTACT_EMAIL,
        "demo_mode": settings.DEMO_MODE,
        "max_apr": settings.MAX_APR,
    }

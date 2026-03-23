from django import template

from core.currency import format_ksh


register = template.Library()


@register.filter
def ksh(value):
    return format_ksh(value)

# promapp/templatetags/markdown_extras.py

from django import template
import markdown2, bleach

register = template.Library()

# Зливаємо frozenset + set
ALLOWED_TAGS = bleach.sanitizer.ALLOWED_TAGS.union({
    "h1", "h2", "h3", "h4",
    "table", "thead", "tbody", "tr", "th", "td"
})

@register.filter
def md(value):
    """
    Перетворює Markdown → безпечний HTML з підтримкою таблиць.
    """
    html = markdown2.markdown(value, extras=["tables", "fenced-code-blocks"])
    # Використовуємо ті ж самі атрибути що й за замовчуванням
    cleaned = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=bleach.sanitizer.ALLOWED_ATTRIBUTES,
        strip=True
    )
    return cleaned

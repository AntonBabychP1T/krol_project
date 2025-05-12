# promapp/templatetags/markdown_extras.py
from django import template
import markdown2
import bleach

register = template.Library()

# базовий whitelist bleach повертає як frozenset → перетворюємо у list,
# а потім розширюємо своїми елементами
ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    "h1", "h2", "h3", "h4",
    "table", "thead", "tbody", "tr", "th", "td",
]

ALLOWED_ATTRS = {
    # дозволимо посиланням target / rel ‑ атрибути
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "a": ["href", "title", "target", "rel"],
    "th": ["align"], "td": ["align"],
}

@register.filter(name="md", is_safe=True)
def markdown_safe(value: str) -> str:
    """
    Конвертує Markdown‑текст у HTML та санітизує результат.
    Тег позначено is_safe=True, бо bleach уже видаляє небезпечне.
    """
    if not value:
        return ""
    html = markdown2.markdown(
        value,
        extras=["tables", "fenced-code-blocks"]
    )
    # очищаємо: прибираємо «не дозволені» теги/атрибути, JS‑обробники тощо
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)

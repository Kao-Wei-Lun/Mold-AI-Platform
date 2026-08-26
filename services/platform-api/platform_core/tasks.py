from celery import shared_task


@shared_task(name="platform_core.echo")
def echo(payload: dict[str, object]) -> dict[str, object]:
    return payload

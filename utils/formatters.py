def format_post(commit: dict, analysis: str) -> str:
    return (
        "[Оригинал коммита]\n"
        f"- Автор: {commit['author']}\n"
        f"- Текст: {commit['text']}\n"
        f"- Дата: {commit['date']}\n"
        f"- Ссылка: {commit['link']}\n\n"
        "\n"
        f"{analysis}"
    )
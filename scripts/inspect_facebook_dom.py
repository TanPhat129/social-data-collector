"""Dump article metadata from one permitted Facebook group for selector debugging.

The output can contain visible group content; it is stored under logs/, which
is ignored by Git. Do not share it publicly.
"""
import argparse
import json
from pathlib import Path

from app.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_url", help="Allowed Facebook group URL to inspect")
    parser.add_argument("--output", default="logs/facebook_dom_debug.json")
    parser.add_argument("--screenshot", default="logs/facebook_dom_debug.png")
    parser.add_argument("--scrolls", type=int, default=2)
    args = parser.parse_args()
    settings = get_settings()
    if not settings.facebook_browser_account_uid:
        parser.error("FACEBOOK_BROWSER_ACCOUNT_UID is required")
    from playwright.sync_api import sync_playwright

    profile = Path(settings.facebook_browser_profile_root) / settings.facebook_browser_account_uid
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(str(profile), headless=True)
        page = context.new_page()
        try:
            page.goto(args.source_url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(3_000)
            for _ in range(args.scrolls):
                page.mouse.wheel(0, 1_200)
                page.wait_for_timeout(1_000)
            rows = []
            for index, article in enumerate(page.locator('[role="article"]').all()[:30]):
                try:
                    rows.append(article.evaluate("""(node, index) => ({
                        index,
                        text: (node.innerText || '').slice(0, 700),
                        attributes: [...node.attributes].filter(a => a.name.startsWith('data-') || a.name === 'aria-label').map(a => [a.name, a.value]),
                        parentArticleCount: [...node.parentElement.closest('body').querySelectorAll('[role="article"]')].filter(a => a.contains(node) && a !== node).length,
                        links: [...node.querySelectorAll('a[href]')].map(a => a.href).filter(h => h.includes('/posts/') || h.includes('story_fbid=')).slice(0, 5),
                        dirAuto: [...node.querySelectorAll('[dir="auto"]')].slice(0, 12).map(item => ({
                            text: (item.innerText || '').slice(0, 350),
                            ancestors: (() => { const values = []; let parent = item.parentElement; while (parent && parent !== node && values.length < 5) { values.push([parent.tagName, parent.getAttribute('role'), parent.getAttribute('aria-label'), parent.getAttribute('data-testid'), parent.getAttribute('data-ad-rendering-role')]); parent = parent.parentElement; } return values; })(),
                        })),
                    })""", index, timeout=1_500))
                except Exception as exc:
                    rows.append({"index": index, "error": type(exc).__name__})
            pagelets = page.locator('[data-pagelet]').evaluate_all("""nodes => nodes
                .filter(node => /feed|group|story/i.test(node.getAttribute('data-pagelet') || ''))
                .slice(0, 30)
                .map(node => ({
                    pagelet: node.getAttribute('data-pagelet'),
                    text: (node.innerText || '').slice(0, 700),
                    links: [...node.querySelectorAll('a[href]')].map(a => a.href)
                        .filter(h => h.includes('/posts/') || h.includes('story_fbid=')).slice(0, 5),
                    attributes: [...node.attributes].map(a => [a.name, a.value]),
                }))""")
            destination = Path(args.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps({"url": page.url, "articles": rows, "pagelets": pagelets}, ensure_ascii=False, indent=2), encoding="utf-8")
            page.screenshot(path=args.screenshot, full_page=True)
            print(f"Wrote {len(rows)} article records to {destination}")
            print(f"Wrote screenshot to {args.screenshot}")
        finally:
            context.close()


if __name__ == "__main__":
    main()

"""Export the in-app guide content as Markdown for repository readers."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'whatsapp_messaging/public/docs/user-guide.json'
OUTPUT = ROOT / 'docs/user-guide'


def main():
    book = json.loads(SOURCE.read_text())
    entries = {g['id']:g for g in book['guides']}
    OUTPUT.mkdir(parents=True,exist_ok=True)
    index = ['# WhatsApp user guide', '', 'Open **User guide** in any WhatsApp workspace or use `/desk/whatsapp-guide` on your site.', '', book['screenshot_notice'], '']
    for category in dict.fromkeys(g['category'] for g in entries.values()):
        index += ['## '+category, '']
        for guide in entries.values():
            if guide['category'] == category:
                index += [f"- [{guide['title']}]({guide['id']}.md) — {guide['summary']}"]
        index += ['']
    index += ['Updated '+book['updated']+'.', '']
    (OUTPUT/'README.md').write_text('\n'.join(index))
    for guide in entries.values():
        lines = ['# '+guide['title'], '', guide['summary'], '', '**Who can do this:** '+guide['audience'], '', '## What this workflow does', '', guide['description'], '', '[All workflows](README.md)', '']
        for i,step in enumerate(guide['steps'],1):
            lines += [f"## {i}. {step['title']}", '', step['detail'], '']
        lines += ['## What to check', '', guide['check'], '', '## If you need help', '', guide['note'], '', '## Screenshots', '']
        for screen in guide['screenshots']:
            lines += [f"![{screen['caption']}](../../whatsapp_messaging/public/docs/screenshots/{screen['file']})", '', screen['caption'], '']
        lines += ['## Related workflows', '']
        lines += [f"- [{entries[id]['title']}]({id}.md)" for id in guide['related']]
        lines += ['',book['screenshot_notice']+' Updated '+book['updated']+'.','']
        (OUTPUT/(guide['id']+'.md')).write_text('\n'.join(lines))
    print(f'Exported {len(entries)} workflow guides')


if __name__ == '__main__':
    main()

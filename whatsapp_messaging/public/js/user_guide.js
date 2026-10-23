import guidebook from '../docs/user-guide.json';

frappe.provide('whatsapp_messaging');
(() => {
    const node = (tag, text, cls) => {
        const element = document.createElement(tag);
        if (text !== undefined) element.textContent = text;
        if (cls) element.className = cls;
        return element;
    };
    const link = (text, id, cls = '') => {
        const a = node('a', text, cls);
        a.href = '/desk/whatsapp-guide' + (id ? '/' + encodeURIComponent(id) : '');
        return a;
    };
    const css = `
.wg-root{padding:24px;max-width:1280px;margin:auto;color:var(--text-color)}
.wg-hero{padding:28px;background:var(--card-bg);border:1px solid var(--border-color);border-radius:14px;margin-bottom:20px}
.wg-eyebrow{font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--text-muted);margin-bottom:10px}
.wg-hero h2,.wg-article h2{font-size:28px;line-height:1.25;margin:0 0 12px;letter-spacing:-.02em}
.wg-intro{font-size:15px;line-height:1.7;max-width:720px;color:var(--text-muted);margin-bottom:16px}
.wg-description{margin:4px 0 22px;font-family:var(--font-stack);color:var(--text-color)}.wg-description h3{font-family:inherit;font-size:var(--text-md);font-weight:600;line-height:1.5;margin:0 0 8px}.wg-description p{font-family:inherit;font-size:var(--text-base);font-weight:400;line-height:1.6;margin:0}
.wg-filters{display:flex;gap:10px;margin:20px 0 12px}.wg-filters input{flex:1}.wg-filters select{max-width:220px}
.wg-count,.wg-footnote{font-size:12px;color:var(--text-muted);line-height:1.6}
.wg-group{margin:26px 0}.wg-group h3{font-size:17px;margin-bottom:14px}
.wg-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(255px,1fr));gap:14px}
.wg-card{display:flex;flex-direction:column;gap:10px;padding:20px;border:1px solid var(--border-color);border-radius:12px;background:var(--card-bg);text-decoration:none!important;color:var(--text-color)!important}
.wg-card:hover,.wg-card:focus-visible{border-color:var(--green-500,#27a568);box-shadow:0 2px 10px #00000008}.wg-card h4{font-size:16px;line-height:1.5;margin:0}.wg-card p{font-size:13px;color:var(--text-muted);line-height:1.65;margin:0;flex:1}
.wg-badge{font-size:11px;padding:4px 8px;border-radius:6px;background:var(--subtle-fg);display:inline-block;width:fit-content;line-height:1.5}
.wg-layout{display:grid;grid-template-columns:220px minmax(0,1fr);gap:32px;align-items:start}
.wg-nav{position:sticky;top:82px;max-height:calc(100vh - 120px);overflow:auto;padding:6px 12px 12px 0}.wg-nav a{display:block;font-size:13px;padding:7px 10px;border-radius:6px;color:var(--text-muted)}.wg-nav a[aria-current=page]{background:var(--subtle-fg);font-weight:600;color:var(--text-color)}.wg-nav h3{font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin:18px 10px 6px;color:var(--text-muted)}
.wg-article{min-width:0;max-width:880px}.wg-back{display:inline-block;margin:0 0 18px;font-size:13px}.wg-article .wg-badge{margin:0 0 16px}.wg-open{margin:0 0 22px}
.wg-figure{margin:0 0 24px;border:1px solid var(--border-color);border-radius:10px;overflow:hidden;background:var(--card-bg)}.wg-figure img{display:block;width:100%;height:auto;max-height:440px;object-fit:contain;cursor:zoom-in}.wg-figure figcaption{font-size:12px;color:var(--text-muted);padding:12px 16px;line-height:1.6}.wg-more-screens{margin:20px 0}.wg-more-screens summary{cursor:pointer;padding:12px 0;font-weight:600}
.wg-steps{padding:0;list-style:none;counter-reset:workflow}.wg-steps li{counter-increment:workflow;position:relative;padding:0 0 20px 42px}.wg-steps li:before{content:counter(workflow);position:absolute;left:0;top:0;width:28px;height:28px;border:1px solid var(--border-color);border-radius:50%;text-align:center;line-height:27px;font-size:12px;font-weight:600;background:var(--card-bg)}.wg-steps h3{font-size:16px;line-height:1.6;margin:0 0 5px}.wg-steps p{font-size:14px;line-height:1.75;margin:0}
.wg-callout{border:1px solid var(--border-color);border-left:3px solid var(--green-500,#27a568);border-radius:8px;padding:16px 20px;margin:0 0 16px;background:var(--card-bg);font-size:14px;line-height:1.75}.wg-callout strong{display:block;margin-bottom:4px}.wg-note{border-left-color:var(--yellow-500,#e4b23a)}
.wg-related{margin-top:26px}.wg-related h3{font-size:16px}.wg-related a{display:block;padding:7px 0}.wg-empty{padding:40px 10px;color:var(--text-muted)}
@media(max-width:850px){.wg-layout{grid-template-columns:1fr}.wg-nav{display:none}.wg-root{padding:16px}.wg-hero{padding:22px}.wg-article h2{font-size:25px}}
@media(max-width:550px){.wg-filters{flex-direction:column}.wg-filters select{max-width:none}.wg-root{padding:10px}.wg-cards{grid-template-columns:1fr}.wg-hero{padding:20px}.wg-steps li{padding-left:38px}.wg-figure figcaption{padding:10px}}
@media print{.wg-nav,.wg-back,.wg-open,.wg-related,.wg-filters,.page-head,.navbar,.desk-sidebar,.standard-sidebar{display:none!important}.wg-layout{display:block}.wg-root{padding:0}.wg-article{max-width:none}.wg-figure,.wg-callout,.wg-steps li{break-inside:avoid}.wg-figure img{max-height:400px;object-fit:contain}}
`;
    const groups = [...new Set(guidebook.guides.map(g => g.category))];
    whatsapp_messaging.UserGuide = class {
        constructor(wrapper) {
            this.page = frappe.ui.make_app_page({parent: wrapper, title: __('WhatsApp User Guide'), single_column: true});
            if (!document.getElementById('whatsapp-guide-style')) {
                const style = node('style', css); style.id = 'whatsapp-guide-style'; document.head.append(style);
            }
            this.root = node('div', undefined, 'wg-root'); this.page.main[0].append(this.root);
            this.show();
        }
        show() {
            const id = frappe.get_route()[1];
            this.root.replaceChildren();
            const guide = guidebook.guides.find(g => g.id === id);
            if (id && !guide) {
                this.page.set_title(__('WhatsApp User Guide'));
                this.root.append(node('h2', 'Guide not found'), node('p', 'Choose a workflow from the user guide.'), link('Browse all workflows'));
            } else if (guide) this.article(guide);
            else this.home();
        }
        home() {
            this.page.set_title(__('WhatsApp User Guide'));
            const hero = node('section', undefined, 'wg-hero');
            hero.append(node('div', 'WhatsApp Messaging · Hospital workflows', 'wg-eyebrow'), node('h2', 'What would you like to do?'), node('p', 'Follow Riverbend Hospital’s patient services team: reply to patients, confirm appointments, send visit instructions and manage reminders. Choose a workflow or search for a task, button or status.', 'wg-intro'));
            const filters = node('div', undefined, 'wg-filters');
            const search = node('input', undefined, 'form-control'); search.type = 'search'; search.placeholder = 'Search workflows, e.g. reply, schedule, Unknown'; search.setAttribute('aria-label', 'Search user guide');
            const category = node('select', undefined, 'form-control'); category.setAttribute('aria-label', 'Workflow category');
            for (const value of ['All workflows', ...groups]) { const option = node('option', value); option.value = value; category.append(option); }
            filters.append(search, category); hero.append(filters);
            const count = node('div', undefined, 'wg-count'); count.setAttribute('role', 'status'); count.setAttribute('aria-live', 'polite'); hero.append(count);
            const results = node('div'); this.root.append(hero, results);
            const render = () => {
                const words = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
                const matching = guidebook.guides.filter(g => (category.value === 'All workflows' || category.value === g.category) && words.every(word => JSON.stringify(g).toLowerCase().includes(word)));
                count.textContent = matching.length + ' of ' + guidebook.guides.length + ' workflows · Roles are listed on each guide';
                results.replaceChildren();
                for (const group of groups) {
                    const entries = matching.filter(g => g.category === group); if (!entries.length) continue;
                    const section = node('section', undefined, 'wg-group'); section.append(node('h3', group));
                    const cards = node('div', undefined, 'wg-cards');
                    for (const guide of entries) {
                        const card = link('', guide.id, 'wg-card'); card.append(node('h4', guide.title), node('p', guide.summary), node('span', guide.audience, 'wg-badge')); cards.append(card);
                    }
                    section.append(cards); results.append(section);
                }
                if (!matching.length) results.append(node('p', 'No workflows match. Try a shorter search or choose All workflows.', 'wg-empty'));
            };
            search.oninput = render; category.onchange = render; render();
            this.root.append(node('p', guidebook.screenshot_notice + ' Updated ' + guidebook.updated + '.', 'wg-footnote'));
        }
        article(guide) {
            this.page.set_title(__(guide.title));
            this.root.append(link('← All workflows', '', 'wg-back'));
            const layout = node('div', undefined, 'wg-layout');
            const navigation = node('nav', undefined, 'wg-nav'); navigation.setAttribute('aria-label', 'Workflow guides');
            for (const group of groups) {
                navigation.append(node('h3', group));
                for (const entry of guidebook.guides.filter(g => g.category === group)) {
                    const a = link(entry.title, entry.id); if (entry.id === guide.id) a.setAttribute('aria-current', 'page'); navigation.append(a);
                }
            }
            const article = node('article', undefined, 'wg-article');
            article.append(node('div', guide.category, 'wg-eyebrow'), node('h2', guide.title), node('p', guide.summary, 'wg-intro'), node('span', 'Who can do this: ' + guide.audience, 'wg-badge'));
            const description = node('section', undefined, 'wg-description');
            description.append(node('h3', 'What this workflow does'), node('p', guide.description)); article.append(description);
            const open = node('div', undefined, 'wg-open');
            const action = node('button', 'Open this workflow', 'btn btn-default btn-sm'); action.type = 'button'; action.onclick = () => frappe.set_route(...guide.route); open.append(action); article.append(open);
            const screenshot = screen => {
                const figure = node('figure', undefined, 'wg-figure'); const a = node('a');
                a.href = '/assets/whatsapp_messaging/docs/screenshots/' + screen.file + '?v=' + guidebook.version; a.target = '_blank'; a.rel = 'noopener'; a.setAttribute('aria-label', 'Enlarge screenshot: ' + screen.caption);
                const image = node('img'); image.src = a.href; image.alt = screen.caption; image.loading = 'lazy'; image.decoding = 'async'; a.append(image);
                image.onerror = () => { image.hidden = true; a.replaceChildren(node('p', 'Screenshot could not load. The steps below are still available.', 'wg-footnote')); };
                figure.append(a, node('figcaption', screen.caption + ' Select the image to enlarge.', '')); return figure;
            };
            article.append(screenshot(guide.screenshots[0]));
            const steps = node('ol', undefined, 'wg-steps');
            for (const step of guide.steps) { const item = node('li'); item.append(node('h3', step.title), node('p', step.detail)); steps.append(item); } article.append(steps);
            if (guide.screenshots.length > 1) {
                const more = node('details', undefined, 'wg-more-screens'); more.append(node('summary', 'More screenshots for this workflow'));
                for (const screen of guide.screenshots.slice(1)) more.append(screenshot(screen)); article.append(more);
            }
            for (const [title, text, cls] of [['What to check', guide.check, 'wg-callout'], ['If you need help', guide.note, 'wg-callout wg-note']]) {
                const box = node('aside', undefined, cls); box.append(node('strong', title), node('span', text)); article.append(box);
            }
            const related = node('section', undefined, 'wg-related'); related.append(node('h3', 'Related workflows'));
            for (const id of guide.related) { const entry = guidebook.guides.find(g => g.id === id); if (entry) related.append(link(entry.title, id)); } article.append(related);
            article.append(node('p', guidebook.screenshot_notice + ' Updated ' + guidebook.updated + '.', 'wg-footnote'));
            layout.append(navigation, article); this.root.append(layout);
        }
    };
})();

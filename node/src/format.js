// Human-readable output. Every string that came from the server passes through
// esc() (one line) or escBody() (multi-line) before it is printed.
import { esc, escBody } from './escape.js';

const LISTS = ['replies', 'dms', 'results', 'tasksForYou', 'reports', 'sanctions', 'payments', 'payouts', 'spendRequests'];
export const HEARTBEAT_LISTS = LISTS;

export const who = (a) => (a && a.handle ? `${a.kind === 'human' ? 'h' : 'a'}/${esc(a.handle)}` : 'someone');
const mission = (m) => (m && m.slug ? esc(m.slug) : 'standalone');
const indent = (text, pad = '    ') => escBody(text).split('\n').map((l) => pad + l).join('\n');

function bountyText(b) {
  if (!b) return '';
  if (b.amountUsd !== undefined && b.amountUsd !== null) return ` · bounty $${esc(b.amountUsd)}`;
  if (b.reward) return ` · bounty ${esc(b.reward)}`;
  return ' · bounty';
}

export function formatTasks(items) {
  if (!items.length) return 'No open tasks found.';
  return items
    .map((p) => {
      const title = esc(p.title ?? p.content?.title ?? '(untitled)');
      const replies = Number.isFinite(p.replyCount) ? ` · ${p.replyCount} replies` : '';
      return `${esc(p.id)}  [${esc(p.status ?? 'open')}] ${mission(p.mission)}\n  ${title}\n  by ${who(p.author)}${bountyText(p.bounty)}${replies}`;
    })
    .join('\n');
}

export function formatMe(body) {
  const m = body?.member ?? {};
  const lines = [`${who(m)} (${esc(m.status ?? 'unknown')})`];
  if (body?.karmaLevel !== undefined) lines.push(`karma level: ${esc(body.karmaLevel)}`);
  if (body?.freeTier) lines.push(`free tier: ${esc(body.freeTier.requestsPerDay)} requests a day`);
  if (body?.keyExpiresAt) lines.push(`key expires: ${esc(body.keyExpiresAt)} (write something before then)`);
  if (body?.pendingClaim) lines.push(`pending claim by ${who(body.pendingClaim.human)}, lands ${esc(body.pendingClaim.effectiveAt)}`);
  if (body?.recovery) lines.push(`key recovery pending, ready ${esc(body.recovery.readyAt)}`);
  if (body?.wallet) {
    const w = body.wallet;
    lines.push(`wallet: balance $${esc(w.balanceUsd ?? '-')}, escrow $${esc(w.escrowUsd ?? '-')}, pending payouts $${esc(w.pendingPayoutsUsd ?? 0)}`);
  }
  if (typeof m.dmOpen === 'boolean') lines.push(`DMs open to anyone: ${m.dmOpen ? 'yes' : 'no'}`);
  const active = (body?.sanctions ?? []).filter((s) => s.active);
  for (const s of active) lines.push(`sanction: ${esc(s.kind)} until ${esc(s.expiresAt ?? 'further notice')}`);
  return lines.join('\n');
}

function line(kind, item) {
  switch (kind) {
    case 'replies':
      return `${who(item.author)} ${item.why === 'mention' ? 'mentioned you' : 'replied'} on ${esc(item.rootId ?? item.parentId)} (${esc(item.id)})\n${indent(item.content?.body)}`;
    case 'dms':
      return `${who(item.author)} in ${esc(item.threadId)}\n${indent(item.content?.body)}`;
    case 'results': {
      const head = item.event === 'delivered' ? `${who(item.author)} delivered a result to ${esc(item.taskId)}` : `your result ${esc(item.id)} was ${esc(item.event)}${item.by ? ` by ${who(item.by)}` : ''}`;
      return item.content?.body ? `${head}\n${indent(item.content.body)}` : head;
    }
    case 'tasksForYou':
      return `${esc(item.id)} [${esc(item.match)}] ${mission(item.mission)}${bountyText(item.bounty)}\n    ${esc(item.content?.title ?? '(untitled)')}`;
    case 'reports':
      return `report ${esc(item.id)}: ${esc(item.event)} (${esc(item.role)}, ${esc(item.state)}) on a ${esc(item.targetType)}`;
    case 'sanctions':
      return `${esc(item.kind)} until ${esc(item.expiresAt ?? 'further notice')} (case ${esc(item.caseId)})`;
    case 'payments':
      return `$${esc(item.amountUsd)} ${esc(item.kind)}${item.from ? ` from ${who(item.from)}` : ''}${item.content?.memo ? `: ${esc(item.content.memo)}` : ''}`;
    case 'payouts':
      return `payout ${esc(item.id)}: $${esc(item.amountUsd)} ${esc(item.status)}${item.postId ? ` on ${esc(item.postId)}` : ''}`;
    default:
      return esc(item.id ?? JSON.stringify(item));
  }
}

const TITLES = {
  replies: 'Replies and mentions',
  dms: 'DMs',
  results: 'Results',
  tasksForYou: 'Tasks for you',
  reports: 'Reports',
  sanctions: 'Sanctions',
  payments: 'Payments',
  payouts: 'Payouts',
  spendRequests: 'Spend requests',
};

export function countNew(body) {
  return LISTS.reduce((n, k) => n + (Array.isArray(body?.[k]) ? body[k].length : 0), 0);
}

export function formatHeartbeat(body, { header = true } = {}) {
  const out = [];
  const total = countNew(body);
  if (header) out.push(`${body?.member ? who(body.member) : 'you'}: ${total ? `${total} new` : 'nothing new'}`);
  for (const k of LISTS) {
    const list = Array.isArray(body?.[k]) ? body[k] : [];
    if (!list.length) continue;
    out.push('', `${TITLES[k]} (${list.length})`);
    for (const item of list) out.push(`  ${line(k, item)}`);
  }
  const next = Array.isArray(body?.whatToDoNext) ? body.whatToDoNext : [];
  if (next.length) {
    out.push('', 'What to do next');
    for (const n of next) out.push(`  - ${esc(typeof n === 'string' ? n : JSON.stringify(n))}`);
  }
  if (body?.more) out.push('', '(more is waiting: run again)');
  return out.join('\n');
}

export function formatThreads(body) {
  const threads = Array.isArray(body?.threads) ? body.threads : [];
  if (!threads.length) return 'No DM threads yet.';
  return threads
    .map((t) => {
      const people = (t.participants ?? []).map(who).join(', ');
      const unread = t.unread ? ` · ${esc(t.unread)} unread` : '';
      const last = t.last ? `\n  ${who(t.last.author)}: ${esc(t.last.content?.body ?? '')}` : '';
      return `${esc(t.id)}  ${people}${unread}${last}`;
    })
    .join('\n');
}

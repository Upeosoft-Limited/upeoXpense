<script setup>
import { ref, reactive, onMounted, inject, watch } from "vue";
import api from "../api.js";
import StatusPill from "../components/StatusPill.vue";
import Drawer from "../components/Drawer.vue";
import { money, shortDate, fromNow } from "../format.js";

const toast = inject("toast");

const FILTERS = ["All", "Draft", "Approved", "Rejected"];
const filter = ref("Draft");
const loading = ref(true);
const rows = ref([]);

const drawerOpen = ref(false);
const detail = reactive({ loading: false, data: null });
const acting = ref(false);
const rejecting = ref(false);
const rejectReason = ref("");

async function load() {
	loading.value = true;
	try {
		const res = await api.get("claims", { status: filter.value });
		rows.value = res.rows;
	} catch (e) {
		toast(e.message || "Could not load claims.", "bad");
	} finally {
		loading.value = false;
	}
}
watch(filter, load);

async function open(name) {
	drawerOpen.value = true;
	detail.loading = true;
	detail.data = null;
	rejecting.value = false;
	rejectReason.value = "";
	try {
		detail.data = await api.get("claim", { name });
	} catch (e) {
		toast(e.message || "Could not open claim.", "bad");
		drawerOpen.value = false;
	} finally {
		detail.loading = false;
	}
}

async function act(action) {
	if (!detail.data) return;
	acting.value = true;
	try {
		const args = { name: detail.data.doc.name, action };
		if (action === "reject") args.reason = rejectReason.value;
		await api.post("claim_action", args);
		toast(action === "approve" ? "Claim approved." : "Claim rejected.", "good");
		await open(detail.data.doc.name);
		await load();
	} catch (e) {
		toast(e.message || "Action failed.", "bad");
	} finally {
		acting.value = false;
	}
}

function statusLabel(r) {
	return r.approval_status || (r.docstatus === 1 ? "Submitted" : "Draft");
}

onMounted(load);
</script>

<template>
	<div class="ux-toolbar">
		<div class="ux-chips">
			<button v-for="f in FILTERS" :key="f" class="ux-chip" :class="{ active: filter === f }" @click="filter = f">
				{{ f === "Draft" ? "Awaiting approval" : f }}
			</button>
		</div>
	</div>

	<div class="ux-card ux-table-wrap">
		<table class="ux-table">
			<thead>
				<tr>
					<th>Claim</th>
					<th>Employee</th>
					<th class="num">Claimed</th>
					<th class="num">Sanctioned</th>
					<th>Status</th>
					<th class="num">Updated</th>
				</tr>
			</thead>
			<tbody>
				<tr v-if="loading"><td colspan="6"><div v-for="i in 5" :key="i" class="ux-skeleton" style="height: 20px; margin: 10px 0"></div></td></tr>
				<tr v-else v-for="r in rows" :key="r.name" class="ux-row" @click="open(r.name)">
					<td>
						<div class="ux-cell-strong">{{ r.name }}</div>
						<div class="ux-cell-dim">{{ shortDate(r.posting_date) }}</div>
					</td>
					<td class="ux-cell-strong">{{ r.employee_name || r.employee }}</td>
					<td class="num ux-cell-strong">{{ money(r.total_claimed_amount) }}</td>
					<td class="num">{{ money(r.total_sanctioned_amount) }}</td>
					<td><StatusPill :status="statusLabel(r)" /></td>
					<td class="num ux-cell-dim">{{ fromNow(r.modified) }}</td>
				</tr>
				<tr v-if="!loading && !rows.length"><td colspan="6"><div class="ux-empty">No claims in this view.</div></td></tr>
			</tbody>
		</table>
	</div>

	<Drawer
		:open="drawerOpen"
		:title="detail.data ? detail.data.doc.name : 'Claim'"
		:subtitle="detail.data ? (detail.data.doc.employee_name || detail.data.doc.employee) : ''"
		@close="drawerOpen = false"
	>
		<div v-if="detail.loading" class="ux-skeleton" style="height: 240px"></div>
		<template v-else-if="detail.data">
			<div class="ux-detail-status">
				<StatusPill :status="detail.data.doc.approval_status || 'Draft'" />
				<span class="ux-cell-dim">{{ shortDate(detail.data.doc.posting_date) }}</span>
			</div>

			<dl class="ux-fields">
				<div><dt>Claimed</dt><dd class="strong">{{ money(detail.data.doc.total_claimed_amount) }}</dd></div>
				<div><dt>Sanctioned</dt><dd>{{ money(detail.data.doc.total_sanctioned_amount) }}</dd></div>
				<div><dt>Company</dt><dd>{{ detail.data.doc.company }}</dd></div>
				<div><dt>Linked receipt</dt><dd>{{ detail.data.linked_receipt || "-" }}</dd></div>
			</dl>

			<h4 class="ux-sub-h">Line items</h4>
			<div class="ux-lines">
				<div v-for="(e, i) in detail.data.expenses" :key="i" class="ux-line">
					<div class="ux-line-main">
						<span class="ux-line-type">{{ e.expense_type }}</span>
						<span class="ux-line-desc">{{ e.description || "-" }}</span>
					</div>
					<div class="ux-line-amt">
						<span>{{ money(e.amount) }}</span>
						<em>{{ shortDate(e.expense_date) }}</em>
					</div>
				</div>
			</div>

			<div v-if="detail.data.doc.remark" class="ux-warn-box">
				<strong>Remark</strong><p>{{ detail.data.doc.remark }}</p>
			</div>

			<div v-if="rejecting" class="ux-correct">
				<label>Reason for rejection (optional)</label>
				<div class="ux-correct-row">
					<input v-model="rejectReason" class="ux-input" placeholder="e.g. Duplicate of RCPT-..." />
				</div>
			</div>
		</template>

		<template #footer v-if="detail.data && detail.data.can_approve && detail.data.doc.approval_status !== 'Approved'">
			<template v-if="!rejecting">
				<button class="ux-btn ux-btn-primary" :disabled="acting" @click="act('approve')">Approve</button>
				<button class="ux-btn ux-btn-danger" :disabled="acting" @click="rejecting = true">Reject</button>
			</template>
			<template v-else>
				<button class="ux-btn ux-btn-danger" :disabled="acting" @click="act('reject')">Confirm rejection</button>
				<button class="ux-btn" :disabled="acting" @click="rejecting = false">Cancel</button>
			</template>
		</template>
	</Drawer>
</template>

<style scoped>
.ux-toolbar { display: flex; align-items: center; gap: 16px; margin-bottom: 18px; flex-wrap: wrap; }
.ux-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.ux-chip { padding: 7px 14px; border-radius: 999px; font-size: 12.5px; font-weight: 600; border: 1px solid var(--ux-border); background: var(--ux-surface); color: var(--ux-text-dim); cursor: pointer; transition: all 0.15s ease; }
.ux-chip:hover { color: var(--ux-text); }
.ux-chip.active { background: #14110a; color: var(--ux-gold-soft); border-color: transparent; }

.ux-table-wrap { overflow-x: auto; }
.ux-table { width: 100%; border-collapse: collapse; }
.ux-table th { text-align: left; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--ux-text-dim); padding: 14px 18px; border-bottom: 1px solid var(--ux-border); }
.ux-table th.num, .ux-table td.num { text-align: right; }
.ux-row { cursor: pointer; transition: background 0.12s ease; }
.ux-row:hover { background: var(--ux-surface-2); }
.ux-table td { padding: 13px 18px; border-bottom: 1px solid var(--ux-border); font-size: 13.5px; }
.ux-row:last-child td { border-bottom: none; }
.ux-cell-strong { font-weight: 600; color: var(--ux-text); }
.ux-cell-dim { font-size: 11.5px; color: var(--ux-text-dim); margin-top: 2px; }
.ux-empty { padding: 40px; text-align: center; color: var(--ux-text-dim); font-size: 13.5px; }

.ux-detail-status { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.ux-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 20px; margin: 0 0 20px; }
.ux-fields dt { font-size: 11px; text-transform: uppercase; letter-spacing: 0.4px; color: var(--ux-text-dim); margin-bottom: 3px; }
.ux-fields dd { margin: 0; font-size: 14px; color: var(--ux-text); font-weight: 500; }
.ux-fields dd.strong { font-weight: 700; }
.ux-sub-h { font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--ux-text-dim); margin: 0 0 10px; }
.ux-lines { display: flex; flex-direction: column; gap: 8px; margin-bottom: 18px; }
.ux-line { display: flex; justify-content: space-between; align-items: center; padding: 12px 14px; background: var(--ux-surface-2); border-radius: 11px; gap: 12px; }
.ux-line-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.ux-line-type { font-size: 13.5px; font-weight: 600; color: var(--ux-text); }
.ux-line-desc { font-size: 11.5px; color: var(--ux-text-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ux-line-amt { display: flex; flex-direction: column; align-items: flex-end; }
.ux-line-amt span { font-size: 13.5px; font-weight: 700; color: var(--ux-text); }
.ux-line-amt em { font-style: normal; font-size: 11px; color: var(--ux-text-dim); }
.ux-warn-box { background: rgba(212, 175, 55, 0.1); border: 1px solid rgba(212, 175, 55, 0.3); border-radius: 11px; padding: 12px 14px; margin-bottom: 18px; font-size: 13px; }
.ux-warn-box strong { display: block; margin-bottom: 6px; color: var(--ux-text); }
.ux-warn-box p { margin: 0; color: var(--ux-text); }
.ux-correct { margin-top: 8px; }
.ux-correct label { display: block; font-size: 12px; color: var(--ux-text-dim); margin-bottom: 6px; font-weight: 600; }
.ux-correct-row { display: flex; gap: 8px; }
.ux-correct-row .ux-input { flex: 1; }

@media (max-width: 620px) { .ux-fields { grid-template-columns: 1fr; } }
</style>

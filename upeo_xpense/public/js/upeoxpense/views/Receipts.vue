<script setup>
import { ref, reactive, onMounted, inject, watch } from "vue";
import api from "../api.js";
import StatusPill from "../components/StatusPill.vue";
import Drawer from "../components/Drawer.vue";
import Modal from "../components/Modal.vue";
import { money, shortDate, fromNow, confidenceBand } from "../format.js";

const toast = inject("toast");
const identity = inject("identity");

const FILTERS = [
	"All",
	"Awaiting Approval",
	"Approved",
	"Reimbursed",
	"Rejected",
	"Failed",
	"Queued",
	"Duplicate",
];
const filter = ref("Awaiting Approval");
const search = ref("");
const loading = ref(true);
const rows = ref([]);
const total = ref(0);

// Drawer state
const drawerOpen = ref(false);
const detail = reactive({ loading: false, data: null });
const correcting = ref(false);
const correctAmount = ref("");
const acting = ref(false);

// Confirm modals
const approveOpen = ref(false);
const rejectOpen = ref(false);
const reimburseOpen = ref(false);
const rejectReason = ref("");
const raiseClaim = ref(false);

function openApprove() {
	raiseClaim.value = !!detail.data.doc.needs_claim;
	approveOpen.value = true;
}
function openReject() {
	rejectReason.value = "";
	rejectOpen.value = true;
}
function openReimburse() {
	reimburseOpen.value = true;
}

let searchTimer = null;

async function load() {
	loading.value = true;
	try {
		const res = await api.get("receipts", { status: filter.value, search: search.value });
		rows.value = res.rows;
		total.value = res.total;
	} catch (e) {
		toast(e.message || "Could not load receipts.", "bad");
	} finally {
		loading.value = false;
	}
}

watch(filter, load);
watch(search, () => {
	clearTimeout(searchTimer);
	searchTimer = setTimeout(load, 300);
});

async function open(name) {
	drawerOpen.value = true;
	detail.loading = true;
	detail.data = null;
	correcting.value = false;
	approveOpen.value = false;
	rejectOpen.value = false;
	reimburseOpen.value = false;
	rejectReason.value = "";
	try {
		detail.data = await api.get("receipt", { name });
	} catch (e) {
		toast(e.message || "Could not open receipt.", "bad");
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
		if (action === "correct") args.amount = Number(correctAmount.value);
		if (action === "reject") args.reason = rejectReason.value;
		if (action === "approve") args.raise_claim = raiseClaim.value ? 1 : 0;
		await api.post("receipt_action", args);
		toast(
			action === "approve"
				? raiseClaim.value
					? "Approved. Held pending reimbursement."
					: "Expense approved and posted."
				: action === "reimburse"
				? "Marked reimbursed. Posted to the expense account."
				: action === "reject"
				? "Expense rejected."
				: "Amount corrected.",
			"good"
		);
		approveOpen.value = false;
		rejectOpen.value = false;
		reimburseOpen.value = false;
		await open(detail.data.doc.name);
		await load();
	} catch (e) {
		toast(e.message || "Action failed.", "bad");
	} finally {
		acting.value = false;
	}
}

function startCorrect() {
	correctAmount.value = detail.data.doc.gross_amount || "";
	correcting.value = true;
}

onMounted(load);
</script>

<template>
	<div class="ux-toolbar">
		<div class="ux-chips">
			<button
				v-for="f in FILTERS"
				:key="f"
				class="ux-chip"
				:class="{ active: filter === f }"
				@click="filter = f"
			>
				{{ f }}
			</button>
		</div>
		<div class="ux-search">
			<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3" stroke-linecap="round"/></svg>
			<input v-model="search" class="ux-search-input" placeholder="Search vendor, phone, ID" />
		</div>
	</div>

	<div class="ux-card ux-table-wrap">
		<table class="ux-table">
			<thead>
				<tr>
					<th>Receipt</th>
					<th>Vendor</th>
					<th class="num">Amount</th>
					<th>Confidence</th>
					<th>Status</th>
					<th class="num">Updated</th>
				</tr>
			</thead>
			<tbody>
				<tr v-if="loading">
					<td colspan="6">
						<div v-for="i in 5" :key="i" class="ux-skeleton" style="height: 20px; margin: 10px 0"></div>
					</td>
				</tr>
				<tr v-else v-for="r in rows" :key="r.name" class="ux-row" @click="open(r.name)">
					<td>
						<div class="ux-cell-strong">{{ r.name }}</div>
						<div class="ux-cell-dim">{{ r.sender_phone || "-" }}</div>
					</td>
					<td>
						<div class="ux-cell-strong">{{ r.vendor_name || "-" }}</div>
						<div class="ux-cell-dim">{{ shortDate(r.receipt_date) }}</div>
					</td>
					<td class="num ux-cell-strong">{{ r.gross_amount ? money(r.gross_amount, r.currency) : "-" }}</td>
					<td>
						<span class="ux-conf" :class="`t-${confidenceBand(r.confidence).tone}`">
							{{ confidenceBand(r.confidence).label }}
							<em v-if="r.confidence">{{ Math.round(r.confidence * 100) }}%</em>
						</span>
					</td>
					<td><StatusPill :status="r.status" /></td>
					<td class="num ux-cell-dim">{{ fromNow(r.modified) }}</td>
				</tr>
				<tr v-if="!loading && !rows.length">
					<td colspan="6">
						<div class="ux-empty">No receipts match this view.</div>
					</td>
				</tr>
			</tbody>
		</table>
	</div>

	<!-- Detail drawer -->
	<Drawer
		:open="drawerOpen"
		:title="detail.data ? (detail.data.doc.vendor_name || 'Receipt') : 'Receipt'"
		:subtitle="detail.data ? detail.data.doc.name : ''"
		@close="drawerOpen = false"
	>
		<div v-if="detail.loading" class="ux-skeleton" style="height: 280px"></div>

		<template v-else-if="detail.data">
			<div class="ux-detail-status">
				<StatusPill :status="detail.data.doc.status" />
				<span v-if="detail.data.doc.confidence" class="ux-conf t-muted">
					Claude confidence {{ Math.round(detail.data.doc.confidence * 100) }}%
				</span>
			</div>

			<div v-if="detail.data.image_url" class="ux-receipt-img">
				<img :src="detail.data.image_url" alt="Receipt image" />
			</div>
			<div v-else class="ux-no-img">Image not available.</div>

			<div v-if="detail.data.validation_errors.length" class="ux-warn-box">
				<strong>Please check</strong>
				<ul>
					<li v-for="(e, i) in detail.data.validation_errors" :key="i">{{ e }}</li>
				</ul>
			</div>

			<div v-if="detail.data.doc.needs_claim" class="ux-flag" :class="{ 'ux-flag-hold': detail.data.doc.status === 'Approved' }">
				<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7" stroke-linecap="round"/></svg>
				<span v-if="detail.data.doc.status === 'Reimbursed'">Reimbursable — refunded to the employee</span>
				<span v-else-if="detail.data.doc.status === 'Approved'">Reimbursable — held pending reimbursement</span>
				<span v-else>Reimbursable — employee paid, to be refunded</span>
			</div>
			<div v-else-if="detail.data.doc.status === 'Approved'" class="ux-flag ux-flag-paid">
				<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.9"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20" stroke-linecap="round"/></svg>
				<span>Company paid — posted to the expense account</span>
			</div>

			<dl class="ux-fields">
				<div><dt>Amount</dt><dd class="strong">{{ detail.data.doc.gross_amount ? money(detail.data.doc.gross_amount, detail.data.doc.currency) : "-" }}</dd></div>
				<div><dt>VAT</dt><dd>{{ detail.data.doc.vat_amount ? money(detail.data.doc.vat_amount, detail.data.doc.currency) : "-" }}</dd></div>
				<div><dt>Date</dt><dd>{{ shortDate(detail.data.doc.receipt_date) }}</dd></div>
				<div><dt>Category</dt><dd>{{ detail.data.doc.expense_claim_type || detail.data.doc.suggested_category || "-" }}</dd></div>
				<div><dt>Payment</dt><dd>{{ detail.data.doc.payment_method || "-" }}</dd></div>
				<div><dt>KRA PIN</dt><dd>{{ detail.data.doc.kra_pin || "-" }}</dd></div>
				<div><dt>eTIMS #</dt><dd>{{ detail.data.doc.etims_invoice_number || "-" }}</dd></div>
				<div><dt>Receipt #</dt><dd>{{ detail.data.doc.receipt_number || "-" }}</dd></div>
				<div><dt>Vendor email</dt><dd>{{ detail.data.doc.vendor_email || "-" }}</dd></div>
				<div><dt>Employee</dt><dd>{{ detail.data.employee_name || detail.data.doc.employee || "-" }}</dd></div>
				<div><dt>Sender</dt><dd>{{ detail.data.doc.sender_phone || "-" }}</dd></div>
			</dl>

			<div v-if="detail.data.line_items && detail.data.line_items.length" class="ux-items">
				<h4 class="ux-sub-h">What was bought</h4>
				<div v-for="(it, i) in detail.data.line_items" :key="i" class="ux-item">
					<span class="ux-item-desc">
						<em v-if="it.qty">{{ it.qty }}&times;</em> {{ it.description }}
					</span>
					<span class="ux-item-amt">{{ it.amount ? money(it.amount, detail.data.doc.currency) : "" }}</span>
				</div>
			</div>

			<div v-if="detail.data.doc.status === 'Rejected' && detail.data.doc.rejection_reason" class="ux-warn-box error">
				<strong>Rejected</strong>
				<p>{{ detail.data.doc.rejection_reason }}</p>
			</div>

			<div v-if="detail.data.doc.decided_by" class="ux-claim-link">
				<span>{{ detail.data.doc.status === 'Rejected' ? 'Decided by' : 'Approved by' }}</span>
				<strong>{{ detail.data.doc.decided_by }}</strong>
			</div>

			<div v-if="detail.data.doc.status === 'Reimbursed' && detail.data.doc.reimbursed_by" class="ux-claim-link">
				<span>Reimbursed by</span>
				<strong>{{ detail.data.doc.reimbursed_by }}</strong>
			</div>

			<div v-if="detail.data.doc.duplicate_of" class="ux-warn-box">
				<strong>Duplicate</strong>
				<p>Same vendor, amount and date as {{ detail.data.doc.duplicate_of }}.</p>
			</div>

			<div v-if="detail.data.doc.error_message && detail.data.doc.status === 'Failed'" class="ux-warn-box error">
				<strong>Error</strong>
				<p>{{ detail.data.doc.error_message }}</p>
			</div>

			<!-- Correction inline form -->
			<div v-if="correcting" class="ux-correct">
				<label>Correct the amount</label>
				<div class="ux-correct-row">
					<input v-model="correctAmount" class="ux-input" type="number" step="0.01" />
					<button class="ux-btn ux-btn-gold" :disabled="acting" @click="act('correct')">Save</button>
					<button class="ux-btn" @click="correcting = false">Cancel</button>
				</div>
			</div>
		</template>

		<template #footer v-if="detail.data && detail.data.doc.status === 'Awaiting Approval' && detail.data.can_approve">
			<button class="ux-btn ux-btn-primary" :disabled="acting" @click="openApprove">Approve</button>
			<button class="ux-btn" :disabled="acting" @click="startCorrect">Correct amount</button>
			<button class="ux-btn ux-btn-danger" :disabled="acting" @click="openReject">Reject</button>
		</template>
		<template #footer v-else-if="detail.data && detail.data.can_reimburse">
			<button class="ux-btn ux-btn-primary" :disabled="acting" @click="openReimburse">Mark reimbursed</button>
		</template>
	</Drawer>

	<!-- Approve confirm dialog -->
	<Modal
		:open="approveOpen"
		icon="check"
		title="Approve this expense?"
		:subtitle="detail.data ? `${detail.data.doc.vendor_name || 'Receipt'} — ${money(detail.data.doc.gross_amount, detail.data.doc.currency)}` : ''"
		confirm-label="Approve"
		confirm-tone="primary"
		:busy="acting"
		@close="approveOpen = false"
		@confirm="act('approve')"
	>
		<label class="ux-check">
			<input type="checkbox" v-model="raiseClaim" />
			<span>
				Reimbursable — the employee paid and must be refunded
				<em>Held in the reimbursement account until you mark it refunded. Leave unchecked for company-paid (petty cash) — it posts straight to the expense account.</em>
			</span>
		</label>
	</Modal>

	<!-- Reimburse confirm dialog -->
	<Modal
		:open="reimburseOpen"
		icon="check"
		title="Mark as reimbursed?"
		:subtitle="detail.data ? `${detail.data.doc.vendor_name || 'Receipt'} — ${money(detail.data.doc.gross_amount, detail.data.doc.currency)}` : ''"
		confirm-label="Confirm reimbursement"
		confirm-tone="primary"
		:busy="acting"
		@close="reimburseOpen = false"
		@confirm="act('reimburse')"
	>
		<p class="ux-reimburse-note">
			This records the refund to the employee. The amount leaves the temporary hold and is posted to the expense account.
		</p>
	</Modal>

	<!-- Reject confirm dialog -->
	<Modal
		:open="rejectOpen"
		icon="x"
		title="Reject this expense?"
		:subtitle="detail.data ? `${detail.data.doc.vendor_name || 'Receipt'} — ${money(detail.data.doc.gross_amount, detail.data.doc.currency)}` : ''"
		confirm-label="Reject expense"
		confirm-tone="danger"
		:busy="acting"
		@close="rejectOpen = false"
		@confirm="act('reject')"
	>
		<label class="ux-modal-label">Reason (the sender will see this)</label>
		<textarea v-model="rejectReason" class="ux-input ux-textarea" rows="3" placeholder="e.g. Personal expense, not reimbursable"></textarea>
	</Modal>
</template>

<style scoped>
.ux-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 18px; flex-wrap: wrap; }
.ux-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.ux-chip {
	padding: 7px 14px; border-radius: 999px; font-size: 12.5px; font-weight: 600;
	border: 1px solid var(--ux-border); background: var(--ux-surface); color: var(--ux-text-dim);
	cursor: pointer; transition: all 0.15s ease;
}
.ux-chip:hover { color: var(--ux-text); }
.ux-chip.active { background: #14110a; color: var(--ux-gold-soft); border-color: transparent; }
.ux-search { display: flex; align-items: center; gap: 8px; background: var(--ux-surface); border: 1px solid var(--ux-border); border-radius: 10px; padding: 8px 12px; color: var(--ux-text-dim); min-width: 240px; }
.ux-search-input { border: none; outline: none; background: transparent; font-size: 13.5px; color: var(--ux-text); width: 100%; }

.ux-table-wrap { overflow-x: auto; }
.ux-table { width: 100%; border-collapse: collapse; }
.ux-table th {
	text-align: left; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;
	color: var(--ux-text-dim); padding: 14px 18px; border-bottom: 1px solid var(--ux-border);
}
.ux-table th.num, .ux-table td.num { text-align: right; }
.ux-row { cursor: pointer; transition: background 0.12s ease; }
.ux-row:hover { background: var(--ux-surface-2); }
.ux-table td { padding: 13px 18px; border-bottom: 1px solid var(--ux-border); font-size: 13.5px; }
.ux-row:last-child td { border-bottom: none; }
.ux-cell-strong { font-weight: 600; color: var(--ux-text); }
.ux-cell-dim { font-size: 11.5px; color: var(--ux-text-dim); margin-top: 2px; }
.ux-conf { display: inline-flex; align-items: baseline; gap: 5px; font-size: 12.5px; font-weight: 600; }
.ux-conf em { font-style: normal; font-size: 11px; opacity: 0.7; }
.t-good { color: #2f8f5b; } .t-warn { color: #a9791b; } .t-bad { color: #b4452f; } .t-muted { color: var(--ux-text-dim); }
.ux-empty { padding: 40px; text-align: center; color: var(--ux-text-dim); font-size: 13.5px; }

/* Drawer detail */
.ux-detail-status { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.ux-receipt-img { border-radius: 12px; overflow: hidden; border: 1px solid var(--ux-border); background: var(--ux-surface-2); margin-bottom: 18px; }
.ux-receipt-img img { width: 100%; display: block; max-height: 360px; object-fit: contain; }
.ux-no-img { padding: 30px; text-align: center; color: var(--ux-text-dim); background: var(--ux-surface-2); border-radius: 12px; margin-bottom: 18px; font-size: 13px; }
.ux-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 20px; margin: 0 0 18px; }
.ux-fields dt { font-size: 11px; text-transform: uppercase; letter-spacing: 0.4px; color: var(--ux-text-dim); margin-bottom: 3px; }
.ux-fields dd { margin: 0; font-size: 14px; color: var(--ux-text); font-weight: 500; }
.ux-fields dd.strong { font-weight: 700; }
.ux-warn-box { background: rgba(212, 175, 55, 0.1); border: 1px solid rgba(212, 175, 55, 0.3); border-radius: 11px; padding: 12px 14px; margin-bottom: 18px; font-size: 13px; }
.ux-warn-box.error { background: rgba(180, 69, 47, 0.08); border-color: rgba(180, 69, 47, 0.3); }
.ux-warn-box strong { display: block; margin-bottom: 6px; color: var(--ux-text); }
.ux-warn-box ul { margin: 0; padding-left: 18px; color: var(--ux-text); }
.ux-warn-box p { margin: 0; color: var(--ux-text); }
.ux-claim-link { display: flex; align-items: center; gap: 10px; padding: 12px 14px; background: var(--ux-surface-2); border-radius: 11px; font-size: 13px; margin-bottom: 18px; }
.ux-claim-link span { color: var(--ux-text-dim); }
.ux-claim-link strong { color: var(--ux-text); }
.ux-correct { margin-top: 8px; }
.ux-correct label { display: block; font-size: 12px; color: var(--ux-text-dim); margin-bottom: 6px; font-weight: 600; }
.ux-correct-row { display: flex; gap: 8px; }
.ux-correct-row .ux-input { flex: 1; }

/* Reimbursement flag */
.ux-flag {
	display: flex; align-items: center; gap: 9px;
	padding: 10px 14px; margin-bottom: 16px; border-radius: 11px;
	background: rgba(201, 162, 39, 0.12); border: 1px solid rgba(201, 162, 39, 0.3);
	color: #a9791b; font-size: 12.5px; font-weight: 600;
}
.ux-flag-hold { background: rgba(58, 110, 165, 0.12); border-color: rgba(58, 110, 165, 0.32); color: #2f5f95; }
.ux-flag-paid { background: rgba(47, 143, 91, 0.12); border-color: rgba(47, 143, 91, 0.3); color: #2f8f5b; }
.ux-reimburse-note { margin: 0; font-size: 13px; color: var(--ux-text-dim); line-height: 1.5; }

/* What was bought */
.ux-sub-h { font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--ux-text-dim); margin: 0 0 10px; }
.ux-items { margin-bottom: 18px; }
.ux-item {
	display: flex; justify-content: space-between; gap: 12px; align-items: baseline;
	padding: 9px 0; border-top: 1px dashed var(--ux-border);
}
.ux-item:first-of-type { border-top: none; }
.ux-item-desc { font-size: 13.5px; color: var(--ux-text); }
.ux-item-desc em { font-style: normal; color: var(--ux-text-dim); font-weight: 700; margin-right: 3px; }
.ux-item-amt { font-size: 13px; font-weight: 600; color: var(--ux-text); white-space: nowrap; }

/* Modal extras */
.ux-check { display: flex; gap: 10px; align-items: flex-start; cursor: pointer; padding: 12px 14px; border: 1px solid var(--ux-border); border-radius: 12px; background: var(--ux-surface-2); }
.ux-check input { margin-top: 2px; width: 16px; height: 16px; accent-color: var(--ux-gold); }
.ux-check span { font-size: 13.5px; font-weight: 600; color: var(--ux-text); }
.ux-check em { display: block; font-style: normal; font-weight: 400; font-size: 12px; color: var(--ux-text-dim); margin-top: 2px; }
.ux-modal-label { display: block; font-size: 12px; color: var(--ux-text-dim); font-weight: 600; margin-bottom: 6px; }
.ux-textarea { resize: vertical; font-family: inherit; }

@media (max-width: 620px) {
	.ux-fields { grid-template-columns: 1fr; }
	.ux-search { width: 100%; }
}
</style>

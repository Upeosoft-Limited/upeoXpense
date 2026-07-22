<script setup>
import { ref, reactive, computed, onMounted, inject } from "vue";
import api from "../api.js";
import KpiCard from "../components/KpiCard.vue";
import TrendChart from "../components/TrendChart.vue";
import BarList from "../components/BarList.vue";
import DonutChart from "../components/DonutChart.vue";
import StatusPill from "../components/StatusPill.vue";
import { money, compactMoney, shortDate, fromNow } from "../format.js";

const toast = inject("toast");
const loading = ref(true);
const d = reactive({});

const STATUS_COLORS = {
	Queued: "#8a8272",
	Extracting: "#3a6ea5",
	"Awaiting Approval": "#d4af37",
	Approved: "#2f8f5b",
	Reimbursed: "#3a6ea5",
	Rejected: "#b4452f",
	Duplicate: "#b8ad93",
	Failed: "#8a3324",
};

function toSegments(counts) {
	return Object.entries(counts || {}).map(([label, value]) => ({
		label,
		value,
		color: STATUS_COLORS[label] || "#8a8272",
	}));
}
const expenseSegments = computed(() => toSegments(d.expense_status_counts));
const claimSegments = computed(() => toSegments(d.claim_status_counts));

async function load() {
	loading.value = true;
	try {
		Object.assign(d, await api.get("dashboard"));
	} catch (e) {
		toast(e.message || "Could not load the dashboard.", "bad");
	} finally {
		loading.value = false;
	}
}
onMounted(load);
</script>

<template>
	<div v-if="loading" class="ux-grid-kpi">
		<div v-for="i in 4" :key="i" class="ux-skeleton" style="height: 108px"></div>
	</div>

	<template v-else>
		<!-- KPI row -->
		<div class="ux-grid-kpi">
			<KpiCard
				accent
				label="Captured value"
				:value="compactMoney(d.captured_value, d.currency)"
				:sub="`${d.total_receipts} receipts all-time`"
			/>
			<KpiCard
				label="This month"
				:value="d.month_count"
				:sub="`${compactMoney(d.month_value, d.currency)} logged`"
			/>
			<KpiCard
				label="Awaiting approval"
				:value="d.awaiting_approval"
				:sub="d.awaiting_approval ? 'Needs a manager' : 'All clear'"
			/>
			<KpiCard
				label="Needs attention"
				:value="d.failed"
				:sub="d.failed ? 'Failed receipts' : 'No failures'"
			/>
		</div>

		<!-- Settlement row: where approved money sits -->
		<div class="ux-grid-kpi">
			<KpiCard
				label="Pending reimbursement"
				:value="compactMoney(d.pending_reimbursement_value, d.currency)"
				:sub="d.pending_reimbursement_count ? `${d.pending_reimbursement_count} awaiting refund (in hold)` : 'Nothing in hold'"
			/>
			<KpiCard
				label="Reimbursed to employees"
				:value="compactMoney(d.reimbursed_value, d.currency)"
				:sub="`${d.reimbursed || 0} refunded`"
			/>
			<KpiCard
				label="Company paid (petty cash)"
				:value="compactMoney(d.company_paid_value, d.currency)"
				:sub="'Booked straight to expenses'"
			/>
			<KpiCard
				label="In expense accounts"
				:value="compactMoney(d.in_expense_accounts_value, d.currency)"
				:sub="'Recognised on the P&L'"
			/>
		</div>

		<!-- Spend trend -->
		<section class="ux-card ux-panel">
			<div class="ux-panel-head">
				<div>
					<h2 class="ux-section-title">Spend trend</h2>
					<p class="ux-section-sub">Captured receipt value by month</p>
				</div>
			</div>
			<TrendChart :data="d.trend" :currency="d.currency" />
		</section>

		<!-- Two pipelines: company-paid expenses vs reimbursable claims -->
		<div class="ux-grid-2">
			<section class="ux-card ux-panel">
				<div class="ux-panel-head">
					<div>
						<h2 class="ux-section-title">Expenses</h2>
						<p class="ux-section-sub">Company-paid receipts (petty cash)</p>
					</div>
				</div>
				<DonutChart :segments="expenseSegments" caption="expenses" empty-text="No company-paid expenses yet." />
			</section>

			<section class="ux-card ux-panel">
				<div class="ux-panel-head">
					<div>
						<h2 class="ux-section-title">Claims</h2>
						<p class="ux-section-sub">Reimbursable — the employee is refunded</p>
					</div>
				</div>
				<DonutChart :segments="claimSegments" caption="claims" empty-text="No reimbursable claims yet." />
			</section>
		</div>

		<!-- Vendors + categories -->
		<div class="ux-grid-2">
			<section class="ux-card ux-panel">
				<div class="ux-panel-head">
					<h2 class="ux-section-title">Top vendors</h2>
				</div>
				<BarList :items="(d.top_vendors || []).map((v) => ({ label: v.vendor, total: v.total, count: v.count }))" :currency="d.currency" />
			</section>

			<section class="ux-card ux-panel">
				<div class="ux-panel-head">
					<h2 class="ux-section-title">By category</h2>
				</div>
				<BarList :items="d.category_split || []" :currency="d.currency" />
			</section>
		</div>

		<!-- Recent activity -->
		<section class="ux-card ux-panel">
			<div class="ux-panel-head">
				<h2 class="ux-section-title">Recent activity</h2>
			</div>
			<div class="ux-recent">
				<div v-for="r in d.recent" :key="r.name" class="ux-recent-row">
					<div class="ux-recent-main">
						<span class="ux-recent-vendor">{{ r.vendor_name || "Unread receipt" }}</span>
						<span class="ux-recent-meta">{{ r.name }} &middot; {{ shortDate(r.receipt_date) }}</span>
					</div>
					<span class="ux-recent-amt">{{ r.gross_amount ? money(r.gross_amount, r.currency) : "-" }}</span>
					<StatusPill :status="r.status" />
					<span class="ux-recent-time">{{ fromNow(r.modified) }}</span>
				</div>
				<div v-if="!d.recent || !d.recent.length" class="ux-empty">
					No receipts yet. They will appear here as staff send photos on WhatsApp.
				</div>
			</div>
		</section>
	</template>
</template>

<style scoped>
.ux-grid-kpi { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
.ux-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
.ux-panel { padding: 20px 22px; }
.ux-panel-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
.ux-recent { display: flex; flex-direction: column; }
.ux-recent-row {
	display: grid;
	grid-template-columns: 1fr auto auto auto;
	align-items: center;
	gap: 16px;
	padding: 12px 4px;
	border-top: 1px solid var(--ux-border);
}
.ux-recent-row:first-child { border-top: none; }
.ux-recent-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.ux-recent-vendor { font-size: 14px; font-weight: 600; color: var(--ux-text); }
.ux-recent-meta { font-size: 11.5px; color: var(--ux-text-dim); }
.ux-recent-amt { font-size: 13.5px; font-weight: 700; color: var(--ux-text); white-space: nowrap; }
.ux-recent-time { font-size: 11.5px; color: var(--ux-text-dim); white-space: nowrap; min-width: 56px; text-align: right; }
.ux-empty { padding: 28px; text-align: center; color: var(--ux-text-dim); font-size: 13.5px; }

@media (max-width: 980px) {
	.ux-grid-kpi { grid-template-columns: repeat(2, 1fr); }
	.ux-grid-2 { grid-template-columns: 1fr; }
}
@media (max-width: 620px) {
	.ux-recent-row { grid-template-columns: 1fr auto; }
	.ux-recent-time { display: none; }
}
</style>

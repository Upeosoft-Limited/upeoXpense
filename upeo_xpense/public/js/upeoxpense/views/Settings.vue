<script setup>
import { ref, reactive, onMounted, inject } from "vue";
import api from "../api.js";

const toast = inject("toast");
const identity = inject("identity");

const loading = ref(true);
const saving = ref(false);
const testing = ref(false);
const s = reactive({});
const secrets = reactive({ waclient_access_token: "", anthropic_api_key: "" });
const meta = reactive({ waclient_access_token_set: false, anthropic_api_key_set: false, webhook_url: "", expense_claim_types: [], companies: [], cost_centers: [], ledger_accounts: [] });

async function load() {
	loading.value = true;
	try {
		const data = await api.get("settings_get");
		Object.assign(s, {
			waclient_base_url: data.waclient_base_url,
			waclient_instance_id: data.waclient_instance_id,
			default_expense_claim_type: data.default_expense_claim_type,
			default_company: data.default_company,
			default_cost_center: data.default_cost_center,
			company_paid_account: data.company_paid_account,
			reimbursement_hold_account: data.reimbursement_hold_account,
			reimbursement_payable_account: data.reimbursement_payable_account,
			reimbursement_paid_from_account: data.reimbursement_paid_from_account,
			minimum_confidence: data.minimum_confidence,
			maximum_receipt_age_days: data.maximum_receipt_age_days,
			test_phone: data.test_phone,
		});
		Object.assign(meta, {
			waclient_access_token_set: data.waclient_access_token_set,
			anthropic_api_key_set: data.anthropic_api_key_set,
			webhook_url: data.webhook_url,
			expense_claim_types: data.expense_claim_types,
			companies: data.companies,
			cost_centers: data.cost_centers,
			ledger_accounts: data.ledger_accounts,
		});
	} catch (e) {
		toast(e.message || "Could not load settings.", "bad");
	} finally {
		loading.value = false;
	}
}

async function save() {
	saving.value = true;
	try {
		const payload = { ...s };
		if (secrets.waclient_access_token) payload.waclient_access_token = secrets.waclient_access_token;
		if (secrets.anthropic_api_key) payload.anthropic_api_key = secrets.anthropic_api_key;
		await api.post("settings_save", { payload });
		secrets.waclient_access_token = "";
		secrets.anthropic_api_key = "";
		toast("Settings saved.", "good");
		await load();
	} catch (e) {
		toast(e.message || "Could not save.", "bad");
	} finally {
		saving.value = false;
	}
}

async function test() {
	testing.value = true;
	try {
		await api.post("test_connection", { phone: s.test_phone });
		toast("Test message sent via WAClient.", "good");
	} catch (e) {
		toast(e.message || "Test failed.", "bad");
	} finally {
		testing.value = false;
	}
}

function copyWebhook() {
	navigator.clipboard?.writeText(meta.webhook_url).then(() => toast("Webhook URL copied.", "good"));
}

onMounted(load);
</script>

<template>
	<div v-if="!identity.can_manage_settings" class="ux-card ux-locked">
		<h3>Settings are restricted</h3>
		<p>Only a System Manager can view or change UpeoXpense configuration.</p>
	</div>

	<template v-else>
		<div v-if="loading" class="ux-skeleton" style="height: 400px"></div>

		<template v-else>
			<div class="ux-settings-grid">
				<!-- WhatsApp / WAClient -->
				<section class="ux-card ux-fieldset">
					<div class="ux-fs-head">
						<h2 class="ux-section-title">WhatsApp gateway</h2>
						<p class="ux-section-sub">WAClient credentials for sending and receiving</p>
					</div>
					<label class="ux-field">
						<span>Base URL</span>
						<input v-model="s.waclient_base_url" class="ux-input" />
					</label>
					<label class="ux-field">
						<span>Instance ID</span>
						<input v-model="s.waclient_instance_id" class="ux-input" />
					</label>
					<label class="ux-field">
						<span>Access token
							<em v-if="meta.waclient_access_token_set" class="ux-set">set</em>
							<em v-else class="ux-unset">not set</em>
						</span>
						<input v-model="secrets.waclient_access_token" class="ux-input" type="password" placeholder="Leave blank to keep current" autocomplete="off" />
					</label>
					<div class="ux-webhook">
						<span class="ux-field-label">Incoming webhook URL</span>
						<div class="ux-webhook-row">
							<code>{{ meta.webhook_url }}</code>
							<button class="ux-btn" @click="copyWebhook">Copy</button>
						</div>
						<p class="ux-hint">Point WAClient's webhook here to receive receipt photos.</p>
					</div>
				</section>

				<!-- Anthropic -->
				<section class="ux-card ux-fieldset">
					<div class="ux-fs-head">
						<h2 class="ux-section-title">Claude (Anthropic)</h2>
						<p class="ux-section-sub">Reads receipts. The key is stored encrypted.</p>
					</div>
					<label class="ux-field">
						<span>API key
							<em v-if="meta.anthropic_api_key_set" class="ux-set">set</em>
							<em v-else class="ux-unset">not set</em>
						</span>
						<input v-model="secrets.anthropic_api_key" class="ux-input" type="password" placeholder="Leave blank to keep current" autocomplete="off" />
					</label>
					<label class="ux-field">
						<span>Minimum confidence</span>
						<input v-model.number="s.minimum_confidence" class="ux-input" type="number" step="0.05" min="0" max="1" />
						<em class="ux-hint">Below this, a receipt is retried on a stronger model.</em>
					</label>
					<label class="ux-field">
						<span>Maximum receipt age (days)</span>
						<input v-model.number="s.maximum_receipt_age_days" class="ux-input" type="number" min="1" />
					</label>
				</section>

				<!-- Defaults -->
				<section class="ux-card ux-fieldset">
					<div class="ux-fs-head">
						<h2 class="ux-section-title">Expense defaults</h2>
						<p class="ux-section-sub">Used when a vendor is not mapped</p>
					</div>
					<label class="ux-field">
						<span>Default company</span>
						<select v-model="s.default_company" class="ux-select">
							<option value="">-- Select --</option>
							<option v-for="c in meta.companies" :key="c" :value="c">{{ c }}</option>
						</select>
					</label>
					<label class="ux-field">
						<span>Default expense claim type</span>
						<select v-model="s.default_expense_claim_type" class="ux-select">
							<option value="">-- Select --</option>
							<option v-for="t in meta.expense_claim_types" :key="t" :value="t">{{ t }}</option>
						</select>
						<em v-if="!meta.expense_claim_types.length" class="ux-hint warn">No Expense Claim Types exist yet. Create one (with a default account per company) in the admin desk.</em>
					</label>
					<label class="ux-field">
						<span>Default cost center</span>
						<select v-model="s.default_cost_center" class="ux-select">
							<option value="">-- Select --</option>
							<option v-for="c in meta.cost_centers" :key="c" :value="c">{{ c }}</option>
						</select>
						<em class="ux-hint">Booked against every posting. Required to record an expense.</em>
					</label>
				</section>

				<!-- Reimbursement & posting accounts -->
				<section class="ux-card ux-fieldset">
					<div class="ux-fs-head">
						<h2 class="ux-section-title">Posting accounts</h2>
						<p class="ux-section-sub">Where money is booked as expenses move through approval and reimbursement</p>
					</div>
					<label class="ux-field">
						<span>Company paid from (petty cash)</span>
						<select v-model="s.company_paid_account" class="ux-select">
							<option value="">-- Select account --</option>
							<option v-for="a in meta.ledger_accounts" :key="a" :value="a">{{ a }}</option>
						</select>
						<em class="ux-hint">Credited when a company-paid expense is approved. It hits the category account immediately.</em>
					</label>
					<label class="ux-field">
						<span>Reimbursement hold</span>
						<select v-model="s.reimbursement_hold_account" class="ux-select">
							<option value="">-- Select account --</option>
							<option v-for="a in meta.ledger_accounts" :key="a" :value="a">{{ a }}</option>
						</select>
						<em class="ux-hint">Temporary account holding approved reimbursables until the employee is refunded.</em>
					</label>
					<label class="ux-field">
						<span>Reimbursement payable</span>
						<select v-model="s.reimbursement_payable_account" class="ux-select">
							<option value="">-- Select account --</option>
							<option v-for="a in meta.ledger_accounts" :key="a" :value="a">{{ a }}</option>
						</select>
						<em class="ux-hint">Liability for what the company owes employees for approved reimbursables.</em>
					</label>
					<label class="ux-field">
						<span>Reimbursement paid from</span>
						<select v-model="s.reimbursement_paid_from_account" class="ux-select">
							<option value="">-- Select account --</option>
							<option v-for="a in meta.ledger_accounts" :key="a" :value="a">{{ a }}</option>
						</select>
						<em class="ux-hint">Cash or bank the refund is paid out of when an expense is marked reimbursed.</em>
					</label>
				</section>

				<!-- Test -->
				<section class="ux-card ux-fieldset">
					<div class="ux-fs-head">
						<h2 class="ux-section-title">Test connection</h2>
						<p class="ux-section-sub">Send yourself a WhatsApp message</p>
					</div>
					<label class="ux-field">
						<span>Test phone (digits only)</span>
						<input v-model="s.test_phone" class="ux-input" placeholder="2547XXXXXXXX" />
					</label>
					<button class="ux-btn ux-btn-gold" :disabled="testing || !s.test_phone" @click="test">
						{{ testing ? "Sending..." : "Send test message" }}
					</button>
				</section>
				</div>

				<div class="ux-save-bar">
					<button class="ux-btn ux-btn-primary" :disabled="saving" @click="save">
						{{ saving ? "Saving..." : "Save settings" }}
					</button>
				</div>
		</template>
	</template>
</template>

<style scoped>
.ux-settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.ux-fieldset { padding: 22px 24px; display: flex; flex-direction: column; gap: 16px; }
.ux-fs-head { margin-bottom: 2px; }
.ux-field { display: flex; flex-direction: column; gap: 7px; }
.ux-field > span, .ux-field-label { font-size: 12.5px; font-weight: 600; color: var(--ux-text); display: flex; align-items: center; gap: 8px; }
.ux-set { font-style: normal; font-size: 10.5px; font-weight: 700; color: #2f8f5b; background: rgba(47, 143, 91, 0.12); padding: 2px 7px; border-radius: 999px; text-transform: uppercase; letter-spacing: 0.4px; }
.ux-unset { font-style: normal; font-size: 10.5px; font-weight: 700; color: #b4452f; background: rgba(180, 69, 47, 0.12); padding: 2px 7px; border-radius: 999px; text-transform: uppercase; letter-spacing: 0.4px; }
.ux-hint { font-size: 11.5px; color: var(--ux-text-dim); font-style: normal; }
.ux-hint.warn { color: #a9791b; }
.ux-webhook { display: flex; flex-direction: column; gap: 7px; }
.ux-webhook-row { display: flex; gap: 8px; align-items: stretch; }
.ux-webhook-row code { flex: 1; background: var(--ux-surface-2); border: 1px solid var(--ux-border); border-radius: 10px; padding: 9px 12px; font-size: 11.5px; color: var(--ux-text); overflow-x: auto; white-space: nowrap; font-family: "SF Mono", ui-monospace, monospace; }
.ux-save-bar { position: sticky; bottom: 0; margin-top: 20px; padding: 16px 0; display: flex; justify-content: flex-end; }
.ux-locked { padding: 48px; text-align: center; }
.ux-locked h3 { margin: 0 0 8px; color: var(--ux-text); }
.ux-locked p { margin: 0; color: var(--ux-text-dim); }
@media (max-width: 860px) { .ux-settings-grid { grid-template-columns: 1fr; } }
</style>

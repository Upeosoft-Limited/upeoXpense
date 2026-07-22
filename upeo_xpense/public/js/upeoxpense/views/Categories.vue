<script setup>
import { ref, reactive, onMounted, inject } from "vue";
import api from "../api.js";
import Modal from "../components/Modal.vue";

const toast = inject("toast");
const identity = inject("identity");

const loading = ref(true);
const company = ref("");
const cats = ref([]);
const accounts = ref([]);
const groups = ref([]);
const busy = ref(""); // name being saved/deleted, or "__new__" / "__acct__"

const newCat = reactive({ name: "", account: "" });
const newAcct = reactive({ name: "", parent: "" });
const acctOpen = ref(false);

function openAcct() {
	newAcct.name = "";
	newAcct.parent = "";
	acctOpen.value = true;
}

// delete confirmation
const delOpen = ref(false);
const delTarget = ref("");

function apply(data) {
	if (!data) return;
	cats.value = data.categories || [];
	accounts.value = data.accounts || [];
	groups.value = data.account_groups || [];
	company.value = data.company || "";
}

async function load() {
	loading.value = true;
	try {
		apply(await api.get("expense_categories"));
	} catch (e) {
		toast(e.message || "Could not load categories.", "bad");
	} finally {
		loading.value = false;
	}
}

async function saveCat(name, account) {
	busy.value = name;
	try {
		apply(await api.post("expense_category_save", { payload: { expense_claim_type: name, account } }));
		toast("Category saved.", "good");
	} catch (e) {
		toast(e.message || "Could not save.", "bad");
		await load();
	} finally {
		busy.value = "";
	}
}

async function addCat() {
	const name = newCat.name.trim();
	if (!name) return;
	busy.value = "__new__";
	try {
		apply(await api.post("expense_category_save", { payload: { expense_claim_type: name, account: newCat.account } }));
		newCat.name = "";
		newCat.account = "";
		toast("Category created.", "good");
	} catch (e) {
		toast(e.message || "Could not create category.", "bad");
	} finally {
		busy.value = "";
	}
}

function askDelete(name) {
	delTarget.value = name;
	delOpen.value = true;
}

async function confirmDelete() {
	busy.value = delTarget.value;
	try {
		apply(await api.post("expense_category_delete", { name: delTarget.value }));
		toast("Category deleted.", "good");
		delOpen.value = false;
	} catch (e) {
		toast(e.message || "Could not delete.", "bad");
	} finally {
		busy.value = "";
	}
}

async function createAccount() {
	const name = newAcct.name.trim();
	if (!name || !newAcct.parent) {
		toast("Enter an account name and a group.", "bad");
		return;
	}
	busy.value = "__acct__";
	try {
		const data = await api.post("expense_account_create", {
			payload: { account_name: name, parent_account: newAcct.parent },
		});
		apply(data);
		toast(`Account "${data.created_account}" created.`, "good");
		acctOpen.value = false;
	} catch (e) {
		toast(e.message || "Could not create account.", "bad");
	} finally {
		busy.value = "";
	}
}

onMounted(load);
</script>

<template>
	<div v-if="!identity.is_manager && !identity.can_manage_settings" class="ux-card ux-locked">
		<h3>Categories are restricted</h3>
		<p>Only a manager can manage expense categories and accounts.</p>
	</div>

	<template v-else>
		<div v-if="loading" class="ux-skeleton" style="height: 420px"></div>

		<template v-else>
			<div class="ux-cat-top">
				<p class="ux-cat-intro">
					Manage the categories receipts are filed under and the chart-of-accounts they post to<template v-if="company"> for {{ company }}</template>.
				</p>
				<button class="ux-btn ux-btn-primary" @click="openAcct">+ New account</button>
			</div>

			<section class="ux-card ux-fieldset">
				<div class="ux-fs-head">
					<h2 class="ux-section-title">Expense categories</h2>
					<p class="ux-section-sub">
						Each category posts to a real account in the chart of accounts<template v-if="company"> for {{ company }}</template>.
					</p>
				</div>

				<div class="ux-cat-table">
					<div class="ux-cat-row ux-cat-head">
						<span>Category</span>
						<span>Posts to account</span>
						<span></span>
					</div>
					<div v-for="c in cats" :key="c.name" class="ux-cat-row">
						<span class="ux-cat-name">{{ c.name }}</span>
						<select v-model="c.account" class="ux-select" :class="{ 'ux-warn-border': !c.account }">
							<option value="">-- Not mapped --</option>
							<option v-for="a in accounts" :key="a" :value="a">{{ a }}</option>
						</select>
						<div class="ux-cat-actions">
							<button class="ux-btn" :disabled="busy === c.name" @click="saveCat(c.name, c.account)">
								{{ busy === c.name ? "Saving..." : "Save" }}
							</button>
							<button class="ux-btn ux-btn-ghost-danger" :disabled="busy === c.name" title="Delete this category" @click="askDelete(c.name)">
								Delete
							</button>
						</div>
					</div>
					<p v-if="!cats.length" class="ux-hint">No categories yet. Add one below.</p>
				</div>

				<div class="ux-cat-add">
					<span class="ux-field-label">Add a category</span>
					<div class="ux-cat-row">
						<input v-model="newCat.name" class="ux-input" placeholder="e.g. Software Subscriptions" @keyup.enter="addCat" />
						<select v-model="newCat.account" class="ux-select">
							<option value="">-- Select account --</option>
							<option v-for="a in accounts" :key="a" :value="a">{{ a }}</option>
						</select>
						<button class="ux-btn ux-btn-gold" :disabled="busy === '__new__' || !newCat.name.trim()" @click="addCat">
							{{ busy === '__new__' ? "Adding..." : "Add" }}
						</button>
					</div>
					<em class="ux-hint">A category with no account cannot be posted to a claim. A category can only be deleted when nothing uses it.</em>
				</div>
			</section>
		</template>
	</template>

	<!-- Create an account in the chart of accounts -->
	<Modal
		:open="acctOpen"
		title="New expense account"
		subtitle="Adds a ledger to the chart of accounts so you can map a category to it."
		confirm-label="Create account"
		confirm-tone="primary"
		icon="check"
		:busy="busy === '__acct__'"
		@close="acctOpen = false"
		@confirm="createAccount"
	>
		<div class="ux-acct-form">
			<label class="ux-field">
				<span>Account name</span>
				<input v-model="newAcct.name" class="ux-input" placeholder="e.g. Software Subscriptions" @keyup.enter="createAccount" />
			</label>
			<label class="ux-field">
				<span>Create under group</span>
				<select v-model="newAcct.parent" class="ux-select">
					<option value="">-- Select group account --</option>
					<option v-for="g in groups" :key="g" :value="g">{{ g }}</option>
				</select>
				<em class="ux-hint">The new account inherits the profit-and-loss placement of its group.</em>
			</label>
		</div>
	</Modal>

	<Modal
		:open="delOpen"
		title="Delete category?"
		:subtitle="`“${delTarget}” will be removed. This only works if no receipt, claim, or vendor mapping uses it.`"
		confirm-label="Delete category"
		confirm-tone="danger"
		icon="x"
		:busy="busy === delTarget"
		@close="delOpen = false"
		@confirm="confirmDelete"
	/>
</template>

<style scoped>
.ux-fieldset { padding: 22px 24px; display: flex; flex-direction: column; gap: 16px; max-width: 920px; }
.ux-fs-head { margin-bottom: 2px; }
.ux-field { display: flex; flex-direction: column; gap: 7px; }
.ux-field > span, .ux-field-label { font-size: 12.5px; font-weight: 600; color: var(--ux-text); display: flex; align-items: center; gap: 8px; }
.ux-hint { font-size: 11.5px; color: var(--ux-text-dim); font-style: normal; }

.ux-cat-table { display: flex; flex-direction: column; gap: 8px; }
.ux-cat-row { display: grid; grid-template-columns: 1fr 1.4fr auto; gap: 12px; align-items: center; }
.ux-cat-head { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--ux-text-dim); padding: 0 2px 2px; }
.ux-cat-name { font-size: 13px; font-weight: 600; color: var(--ux-text); }
.ux-cat-actions { display: flex; gap: 6px; }
.ux-warn-border { border-color: #d9a441 !important; }
.ux-btn-ghost-danger { color: #b4452f; border-color: rgba(180, 69, 47, 0.4); background: transparent; }
.ux-btn-ghost-danger:hover:not(:disabled) { background: rgba(180, 69, 47, 0.1); }
.ux-cat-add { margin-top: 18px; padding-top: 16px; border-top: 1px solid var(--ux-border); display: flex; flex-direction: column; gap: 10px; }

.ux-cat-top { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 14px; max-width: 920px; }
.ux-cat-intro { margin: 0; font-size: 13px; color: var(--ux-text-dim); line-height: 1.5; }
.ux-cat-top .ux-btn-primary { flex-shrink: 0; white-space: nowrap; }
.ux-acct-form { display: flex; flex-direction: column; gap: 14px; padding: 6px 0 2px; }

.ux-locked { padding: 48px; text-align: center; }
.ux-locked h3 { margin: 0 0 8px; color: var(--ux-text); }
.ux-locked p { margin: 0; color: var(--ux-text-dim); }
@media (max-width: 720px) { .ux-cat-row { grid-template-columns: 1fr; } }
</style>

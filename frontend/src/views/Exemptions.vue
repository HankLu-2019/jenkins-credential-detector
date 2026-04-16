<template>
  <div>
    <h1 class="page-title">Exemptions</h1>

    <!-- Add form -->
    <div class="card" style="margin-bottom: 20px">
      <h2 class="section-title">Add Exemption</h2>
      <div class="form-grid">
        <div class="filter-group">
          <label
            >Job name pattern
            <span class="hint">(% wildcard, blank = all)</span></label
          >
          <input
            v-model="form.job_name_pattern"
            placeholder="e.g. my-job% or blank"
          />
        </div>
        <div class="filter-group">
          <label>Finding type <span class="hint">(blank = all)</span></label>
          <input
            v-model="form.finding_type"
            placeholder="e.g. GENERIC_PASSWORD"
          />
        </div>
        <div class="filter-group">
          <label
            >Content hash
            <span class="hint">(SHA256, blank = match by type)</span></label
          >
          <input
            v-model="form.content_hash"
            placeholder="optional"
            class="mono"
          />
        </div>
        <div class="filter-group">
          <label>Reason</label>
          <input v-model="form.reason" placeholder="why is this exempted?" />
        </div>
        <div class="filter-group">
          <label>Created by</label>
          <input v-model="form.created_by" placeholder="your name / email" />
        </div>
        <div class="filter-group">
          <label
            >Expires at <span class="hint">(blank = permanent)</span></label
          >
          <input v-model="form.expires_at" type="datetime-local" />
        </div>
      </div>
      <div
        style="margin-top: 14px; display: flex; gap: 10px; align-items: center"
      >
        <button class="btn btn-primary" @click="submit" :disabled="saving">
          {{ saving ? "Saving…" : "Add Exemption" }}
        </button>
        <span v-if="saveError" class="error-msg" style="padding: 4px 10px">{{
          saveError
        }}</span>
        <span v-if="saveOk" style="color: #1e8449; font-size: 0.9rem"
          >Saved.</span
        >
      </div>
    </div>

    <!-- List -->
    <div class="card">
      <h2 class="section-title">Active Exemptions ({{ exemptions.length }})</h2>
      <div v-if="loading" class="loading">Loading...</div>
      <div v-else-if="error" class="error-msg">{{ error }}</div>
      <div v-else-if="exemptions.length === 0" class="empty">
        No exemptions defined.
      </div>
      <table v-else>
        <thead>
          <tr>
            <th>Job pattern</th>
            <th>Finding type</th>
            <th>Content hash</th>
            <th>Reason</th>
            <th>By</th>
            <th>Expires</th>
            <th>Created</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="e in exemptions"
            :key="e.id"
            :class="isExpired(e) ? 'row-expired' : ''"
          >
            <td class="mono">{{ e.job_name_pattern || "*" }}</td>
            <td class="mono">{{ e.finding_type || "*" }}</td>
            <td class="mono hash-cell">
              {{ e.content_hash ? e.content_hash.slice(0, 12) + "…" : "*" }}
            </td>
            <td>{{ e.reason || "—" }}</td>
            <td>{{ e.created_by || "—" }}</td>
            <td :class="isExpired(e) ? 'text-expired' : ''">
              {{ e.expires_at ? fmtDate(e.expires_at) : "Never" }}
            </td>
            <td style="white-space: nowrap">{{ fmtDate(e.created_at) }}</td>
            <td>
              <button class="btn btn-sm btn-danger" @click="remove(e.id)">
                Delete
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { exemptionsApi } from "../api.js";

const exemptions = ref([]);
const loading = ref(true);
const error = ref(null);
const saving = ref(false);
const saveError = ref(null);
const saveOk = ref(false);

const form = ref({
  job_name_pattern: "",
  finding_type: "",
  content_hash: "",
  reason: "",
  created_by: "",
  expires_at: "",
});

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const res = await exemptionsApi.list();
    exemptions.value = res.data;
  } catch (e) {
    error.value = "Failed to load: " + (e.message || e);
  } finally {
    loading.value = false;
  }
}

async function submit() {
  saving.value = true;
  saveError.value = null;
  saveOk.value = false;
  try {
    const body = {
      job_name_pattern: form.value.job_name_pattern || null,
      finding_type: form.value.finding_type || null,
      content_hash: form.value.content_hash || null,
      reason: form.value.reason,
      created_by: form.value.created_by,
      expires_at: form.value.expires_at
        ? new Date(form.value.expires_at).toISOString()
        : null,
    };
    await exemptionsApi.create(body);
    form.value = {
      job_name_pattern: "",
      finding_type: "",
      content_hash: "",
      reason: "",
      created_by: "",
      expires_at: "",
    };
    saveOk.value = true;
    setTimeout(() => (saveOk.value = false), 2500);
    load();
  } catch (e) {
    saveError.value = e.response?.data?.detail || e.message;
  } finally {
    saving.value = false;
  }
}

async function remove(id) {
  if (!confirm("Delete this exemption?")) return;
  try {
    await exemptionsApi.delete(id);
    load();
  } catch (e) {
    alert("Delete failed: " + (e.message || e));
  }
}

function fmtDate(iso) {
  return iso ? new Date(iso).toLocaleString() : "—";
}
function isExpired(e) {
  return e.expires_at && new Date(e.expires_at) < new Date();
}

onMounted(load);
</script>

<style scoped>
.section-title {
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 14px;
}
.hint {
  color: #aaa;
  font-size: 0.78rem;
  font-weight: 400;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.hash-cell {
  font-size: 0.8rem;
  color: #666;
}
.row-expired td {
  opacity: 0.5;
}
.text-expired {
  color: #c0392b;
}
</style>

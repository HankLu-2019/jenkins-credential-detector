<template>
  <div>
    <h1 class="page-title">Findings</h1>

    <div class="filter-row card" style="margin-bottom: 20px">
      <div class="filter-group">
        <label>Severity</label>
        <select v-model="filters.severity" @change="load">
          <option value="">All</option>
          <option>CRITICAL</option>
          <option>HIGH</option>
          <option>MEDIUM</option>
          <option>LOW</option>
        </select>
      </div>
      <div class="filter-group">
        <label>Job name</label>
        <input
          v-model="filters.job_name"
          placeholder="partial match"
          @keyup.enter="load"
        />
      </div>
      <div class="filter-group">
        <label>Type</label>
        <input
          v-model="filters.finding_type"
          placeholder="e.g. AWS_ACCESS_KEY"
          @keyup.enter="load"
        />
      </div>
      <div class="filter-group">
        <label>&nbsp;</label>
        <label
          style="display: flex; align-items: center; gap: 6px; cursor: pointer"
        >
          <input type="checkbox" v-model="filters.open_only" @change="load" />
          Open only
        </label>
      </div>
      <div class="filter-group">
        <label>&nbsp;</label>
        <button class="btn btn-primary" @click="load">Filter</button>
      </div>
    </div>

    <div v-if="loading" class="loading">Loading...</div>
    <div v-else-if="error" class="error-msg">{{ error }}</div>
    <div v-else class="card">
      <div v-if="findings.length === 0" class="empty">
        No findings match the current filters.
      </div>
      <table v-else>
        <thead>
          <tr>
            <th>Severity</th>
            <th>Type</th>
            <th>Job / Build</th>
            <th>Value (masked)</th>
            <th>Detector</th>
            <th>Detected</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="f in findings"
            :key="f.id"
            :class="f.exemption_id ? 'row-exempted' : ''"
          >
            <td>
              <span class="badge" :class="`badge-${f.severity}`">{{
                f.severity
              }}</span>
            </td>
            <td class="mono">{{ f.finding_type }}</td>
            <td>
              <router-link :to="`/builds/${f.build_id}`" class="job-link">
                Build #{{ f.build_id }}
              </router-link>
            </td>
            <td class="mono">{{ f.display_value || "—" }}</td>
            <td>{{ f.detector }}</td>
            <td style="white-space: nowrap">{{ fmtDate(f.created_at) }}</td>
            <td>
              <span v-if="f.exemption_id" class="exempted-label">Exempted</span>
              <button
                v-else
                class="btn btn-sm btn-primary"
                @click="openExemptModal(f)"
              >
                Exempt
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <div class="pagination">
        <button class="btn btn-sm" :disabled="offset === 0" @click="prev">
          ← Prev
        </button>
        <span>Page {{ page }}</span>
        <button
          class="btn btn-sm"
          :disabled="findings.length < limit"
          @click="next"
        >
          Next →
        </button>
      </div>
    </div>

    <!-- Exempt modal -->
    <div
      v-if="exemptTarget"
      class="modal-overlay"
      @click.self="exemptTarget = null"
    >
      <div class="modal card">
        <h2 style="margin-bottom: 14px">Add Exemption</h2>
        <p style="margin-bottom: 10px; font-size: 0.9rem">
          Finding: <strong>{{ exemptTarget.finding_type }}</strong> — value:
          <code class="mono">{{ exemptTarget.display_value }}</code>
        </p>
        <div class="filter-group" style="margin-bottom: 10px">
          <label>Reason</label>
          <input
            v-model="exemptReason"
            placeholder="e.g. test credential"
            style="width: 100%"
          />
        </div>
        <div class="filter-group" style="margin-bottom: 16px">
          <label>Your name / email</label>
          <input
            v-model="exemptBy"
            placeholder="you@example.com"
            style="width: 100%"
          />
        </div>
        <div style="display: flex; gap: 10px">
          <button class="btn btn-primary" @click="submitExempt">Confirm</button>
          <button class="btn" @click="exemptTarget = null">Cancel</button>
        </div>
        <div v-if="exemptError" class="error-msg" style="margin-top: 10px">
          {{ exemptError }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import { findingsApi, exemptionsApi } from "../api.js";

const route = useRoute();

const findings = ref([]);
const loading = ref(false);
const error = ref(null);
const limit = 50;
const offset = ref(0);
const page = ref(1);

const filters = ref({
  severity: "",
  job_name: route.query.job_name || "",
  finding_type: "",
  open_only: false,
});

const exemptTarget = ref(null);
const exemptReason = ref("");
const exemptBy = ref("");
const exemptError = ref(null);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const params = { limit, offset: offset.value };
    if (filters.value.severity) params.severity = filters.value.severity;
    if (filters.value.job_name) params.job_name = filters.value.job_name;
    if (filters.value.finding_type)
      params.finding_type = filters.value.finding_type;
    if (filters.value.open_only) params.open_only = true;
    const res = await findingsApi.list(params);
    findings.value = res.data;
  } catch (e) {
    error.value = "Failed to load findings: " + (e.message || e);
  } finally {
    loading.value = false;
  }
}

function prev() {
  offset.value = Math.max(0, offset.value - limit);
  page.value--;
  load();
}
function next() {
  offset.value += limit;
  page.value++;
  load();
}

function fmtDate(iso) {
  return iso ? new Date(iso).toLocaleString() : "—";
}

function openExemptModal(f) {
  exemptTarget.value = f;
  exemptReason.value = "";
  exemptBy.value = "";
  exemptError.value = null;
}

async function submitExempt() {
  exemptError.value = null;
  try {
    await exemptionsApi.createFromFinding(
      exemptTarget.value.id,
      exemptReason.value,
      exemptBy.value,
    );
    exemptTarget.value = null;
    load();
  } catch (e) {
    exemptError.value = "Failed: " + (e.response?.data?.detail || e.message);
  }
}

onMounted(load);
</script>

<style scoped>
.row-exempted td {
  opacity: 0.5;
}
.exempted-label {
  font-size: 0.78rem;
  color: #888;
  font-style: italic;
}
.job-link {
  color: #4e8cff;
  text-decoration: none;
}
.job-link:hover {
  text-decoration: underline;
}
.pagination {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  justify-content: flex-end;
  font-size: 0.88rem;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal {
  width: 460px;
  max-width: 95vw;
}
</style>

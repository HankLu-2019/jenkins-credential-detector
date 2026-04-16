<template>
  <div>
    <router-link to="/findings" style="color: #4e8cff; font-size: 0.9rem"
      >← Back to Findings</router-link
    >

    <div v-if="loading" class="loading" style="margin-top: 20px">
      Loading...
    </div>
    <div v-else-if="error" class="error-msg" style="margin-top: 20px">
      {{ error }}
    </div>
    <template v-else>
      <h1 class="page-title" style="margin-top: 16px">
        {{ build.job_name }}
        <span style="color: #888">#{{ build.build_number }}</span>
      </h1>

      <!-- Provenance card -->
      <div class="card" style="margin-bottom: 20px">
        <h2 class="section-title">Build Provenance</h2>
        <dl class="dl-grid">
          <dt>Jenkins Instance</dt>
          <dd>{{ build.jenkins_instance_id }}</dd>
          <dt>Trigger</dt>
          <dd>
            <span class="badge" :class="`trigger-${build.trigger_type}`">{{
              build.trigger_type
            }}</span>
          </dd>

          <template v-if="build.trigger_type === 'GERRIT'">
            <dt>Gerrit Change</dt>
            <dd class="mono">
              {{ build.gerrit_change_id }} ({{ build.gerrit_project }})
            </dd>
            <dt>Branch</dt>
            <dd>{{ build.gerrit_branch }}</dd>
            <dt>Patchset</dt>
            <dd>{{ build.gerrit_patchset }}</dd>
            <dt>Owner</dt>
            <dd>
              {{ build.triggered_by_email || build.triggered_by_user || "—" }}
            </dd>
          </template>

          <template v-else-if="build.trigger_type === 'UPSTREAM'">
            <dt>Upstream Job</dt>
            <dd class="mono">{{ build.upstream_job }}</dd>
            <dt>Upstream Build</dt>
            <dd>#{{ build.upstream_build_number }}</dd>
          </template>

          <template v-else-if="build.trigger_type === 'MANUAL'">
            <dt>Triggered by</dt>
            <dd>{{ build.triggered_by_user || "—" }}</dd>
          </template>

          <dt>Started</dt>
          <dd>{{ fmtDate(build.build_started_at) }}</dd>
          <dt>Scanned</dt>
          <dd>{{ fmtDate(build.scanned_at) }}</dd>
          <dt>Log size</dt>
          <dd>{{ fmtBytes(build.log_size_bytes) }}</dd>
          <dt>Status</dt>
          <dd>
            <span class="badge" :class="`scan-${build.scan_status}`">{{
              build.scan_status
            }}</span>
          </dd>
        </dl>
      </div>

      <!-- Findings -->
      <div class="card">
        <h2 class="section-title">Findings ({{ findings.length }})</h2>
        <div v-if="findings.length === 0" class="empty">
          No findings for this build.
        </div>
        <div v-else>
          <div
            v-for="f in findings"
            :key="f.id"
            class="finding-block"
            :class="f.exemption_id ? 'finding-exempted' : ''"
          >
            <div class="finding-header">
              <span class="badge" :class="`badge-${f.severity}`">{{
                f.severity
              }}</span>
              <span class="mono" style="font-weight: 600">{{
                f.finding_type
              }}</span>
              <span style="color: #888; font-size: 0.82rem"
                >line {{ f.line_number || "?" }}</span
              >
              <span style="color: #888; font-size: 0.82rem"
                >· {{ f.detector }}</span
              >
              <span v-if="f.encoding" class="badge badge-enc">{{
                f.encoding
              }}</span>
              <span v-if="f.exemption_id" class="exempted-label">Exempted</span>
              <span
                v-if="f.llm_confidence !== null"
                style="color: #555; font-size: 0.82rem; margin-left: auto"
              >
                LLM confidence: {{ (f.llm_confidence * 100).toFixed(0) }}%
              </span>
            </div>

            <div class="finding-value mono">{{ f.display_value || "—" }}</div>

            <div v-if="f.llm_explanation" class="finding-explanation">
              {{ f.llm_explanation }}
            </div>

            <pre v-if="f.line_context" class="context-block">{{
              f.line_context
            }}</pre>

            <div v-if="!f.exemption_id" style="margin-top: 8px">
              <button
                class="btn btn-sm btn-primary"
                @click="openExemptModal(f)"
              >
                Add Exemption
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Exempt modal -->
    <div
      v-if="exemptTarget"
      class="modal-overlay"
      @click.self="exemptTarget = null"
    >
      <div class="modal card">
        <h2 style="margin-bottom: 14px">Add Exemption</h2>
        <p style="margin-bottom: 10px; font-size: 0.9rem">
          <strong>{{ exemptTarget.finding_type }}</strong> —
          <code class="mono">{{ exemptTarget.display_value }}</code>
        </p>
        <div class="filter-group" style="margin-bottom: 10px">
          <label>Reason</label>
          <input
            v-model="exemptReason"
            style="width: 100%"
            placeholder="e.g. test fixture"
          />
        </div>
        <div class="filter-group" style="margin-bottom: 16px">
          <label>Your name / email</label>
          <input
            v-model="exemptBy"
            style="width: 100%"
            placeholder="you@example.com"
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
import { ref, onMounted } from "vue";
import { useRoute } from "vue-router";
import { buildsApi, findingsApi, exemptionsApi } from "../api.js";

const route = useRoute();
const buildId = route.params.id;

const build = ref(null);
const findings = ref([]);
const loading = ref(true);
const error = ref(null);

const exemptTarget = ref(null);
const exemptReason = ref("");
const exemptBy = ref("");
const exemptError = ref(null);

onMounted(async () => {
  try {
    const [bRes, fRes] = await Promise.all([
      buildsApi.get(buildId),
      findingsApi.list({ build_id: buildId, limit: 200, offset: 0 }),
    ]);
    build.value = bRes.data;
    findings.value = fRes.data;
  } catch (e) {
    error.value = "Failed to load build: " + (e.message || e);
  } finally {
    loading.value = false;
  }
});

function fmtDate(iso) {
  return iso ? new Date(iso).toLocaleString() : "—";
}
function fmtBytes(b) {
  if (!b) return "0 B";
  if (b < 1024) return b + " B";
  if (b < 1048576) return (b / 1024).toFixed(1) + " KB";
  return (b / 1048576).toFixed(1) + " MB";
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
    // Refresh findings
    const fRes = await findingsApi.list({
      build_id: buildId,
      limit: 200,
      offset: 0,
    });
    findings.value = fRes.data;
  } catch (e) {
    exemptError.value = "Failed: " + (e.response?.data?.detail || e.message);
  }
}
</script>

<style scoped>
.section-title {
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 14px;
}

.dl-grid {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 6px 12px;
  font-size: 0.9rem;
}
dt {
  color: #666;
  font-weight: 500;
}

.trigger-GERRIT {
  background: #e8f0fe;
  color: #1a73e8;
}
.trigger-UPSTREAM {
  background: #f3e8fd;
  color: #7b1fa2;
}
.trigger-TIMER {
  background: #e8f5e9;
  color: #2e7d32;
}
.trigger-MANUAL {
  background: #fff8e1;
  color: #f57f17;
}
.trigger-UNKNOWN {
  background: #f0f0f0;
  color: #666;
}

.scan-FINDINGS {
  background: #fde8e8;
  color: #c0392b;
}
.scan-CLEAN {
  background: #eafaf1;
  color: #1e8449;
}
.scan-PENDING {
  background: #f0f0f0;
  color: #666;
}
.scan-ERROR {
  background: #fff3cd;
  color: #856404;
}

.finding-block {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 14px 16px;
  margin-bottom: 14px;
}
.finding-exempted {
  opacity: 0.55;
}
.finding-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.finding-value {
  background: #f8f9fa;
  padding: 4px 8px;
  border-radius: 4px;
  margin-bottom: 6px;
}
.finding-explanation {
  font-size: 0.87rem;
  color: #555;
  margin-bottom: 8px;
}
.context-block {
  background: #1e1e2e;
  color: #cdd6f4;
  padding: 10px 14px;
  border-radius: 5px;
  font-size: 0.82rem;
  overflow-x: auto;
  margin-bottom: 6px;
  white-space: pre-wrap;
  word-break: break-all;
}
.badge-enc {
  background: #e8f0fe;
  color: #1a73e8;
}
.exempted-label {
  font-size: 0.78rem;
  color: #888;
  font-style: italic;
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

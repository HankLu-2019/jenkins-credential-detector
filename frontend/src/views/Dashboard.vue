<template>
  <div>
    <h1 class="page-title">Dashboard</h1>

    <div v-if="loading" class="loading">Loading...</div>
    <div v-else-if="error" class="error-msg">{{ error }}</div>
    <template v-else>
      <!-- Summary cards -->
      <div class="stat-grid">
        <div class="card stat-card">
          <div class="stat-label">Open Findings</div>
          <div
            class="stat-value"
            :class="stats.open_findings > 0 ? 'text-danger' : 'text-ok'"
          >
            {{ stats.open_findings }}
          </div>
        </div>
        <div class="card stat-card severity-card-CRITICAL">
          <div class="stat-label">Critical</div>
          <div class="stat-value text-danger">{{ stats.critical }}</div>
        </div>
        <div class="card stat-card severity-card-HIGH">
          <div class="stat-label">High</div>
          <div class="stat-value text-high">{{ stats.high }}</div>
        </div>
        <div class="card stat-card severity-card-MEDIUM">
          <div class="stat-label">Medium</div>
          <div class="stat-value text-medium">{{ stats.medium }}</div>
        </div>
        <div class="card stat-card severity-card-LOW">
          <div class="stat-label">Low</div>
          <div class="stat-value text-ok">{{ stats.low }}</div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Builds Scanned</div>
          <div class="stat-value">{{ stats.total_builds_scanned }}</div>
        </div>
        <div class="card stat-card">
          <div class="stat-label">Builds w/ Findings</div>
          <div class="stat-value">{{ stats.builds_with_findings }}</div>
        </div>
      </div>

      <!-- Top jobs -->
      <div class="card" style="margin-top: 24px">
        <h2 style="font-size: 1.05rem; font-weight: 600; margin-bottom: 14px">
          Top Jobs by Finding Count
        </h2>
        <div v-if="stats.top_jobs.length === 0" class="empty">
          No findings yet.
        </div>
        <table v-else>
          <thead>
            <tr>
              <th>Job</th>
              <th style="width: 100px">Findings</th>
              <th style="width: 120px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="j in stats.top_jobs" :key="j.job_name">
              <td class="mono">{{ j.job_name }}</td>
              <td>{{ j.count }}</td>
              <td>
                <router-link
                  :to="{ path: '/findings', query: { job_name: j.job_name } }"
                  class="btn btn-primary btn-sm"
                  >View</router-link
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { statsApi } from "../api.js";

const stats = ref(null);
const loading = ref(true);
const error = ref(null);

onMounted(async () => {
  try {
    const res = await statsApi.get();
    stats.value = res.data;
  } catch (e) {
    error.value = "Failed to load stats: " + (e.message || e);
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 16px;
}
.stat-card {
  text-align: center;
}
.stat-label {
  font-size: 0.82rem;
  color: #777;
  margin-bottom: 6px;
}
.stat-value {
  font-size: 2rem;
  font-weight: 700;
}
.text-danger {
  color: #c0392b;
}
.text-high {
  color: #d35400;
}
.text-medium {
  color: #b7950b;
}
.text-ok {
  color: #1e8449;
}
</style>

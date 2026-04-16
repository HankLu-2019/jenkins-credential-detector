<template>
  <div id="sentinel-app">
    <nav class="nav">
      <span class="nav-brand">Jenkins Log Sentinel</span>
      <router-link to="/">Dashboard</router-link>
      <router-link to="/findings">Findings</router-link>
      <router-link to="/exemptions">Exemptions</router-link>
    </nav>
    <main class="main">
      <router-view />
    </main>
  </div>
</template>

<style>
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}
body {
  font-family: system-ui, sans-serif;
  background: #f4f6f9;
  color: #222;
}

.nav {
  background: #1a1a2e;
  color: #fff;
  padding: 0 24px;
  height: 52px;
  display: flex;
  align-items: center;
  gap: 24px;
}
.nav-brand {
  font-weight: 700;
  font-size: 1.1rem;
  margin-right: 16px;
}
.nav a {
  color: #aac4ff;
  text-decoration: none;
  font-size: 0.95rem;
}
.nav a.router-link-active {
  color: #fff;
  border-bottom: 2px solid #4e8cff;
  padding-bottom: 2px;
}

.main {
  padding: 28px 32px;
  max-width: 1200px;
  margin: 0 auto;
}

/* Shared utilities */
.card {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  padding: 20px 24px;
}
.page-title {
  font-size: 1.4rem;
  font-weight: 700;
  margin-bottom: 20px;
}
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.78rem;
  font-weight: 600;
}
.badge-CRITICAL {
  background: #fde8e8;
  color: #c0392b;
}
.badge-HIGH {
  background: #fef0e6;
  color: #d35400;
}
.badge-MEDIUM {
  background: #fefbe6;
  color: #b7950b;
}
.badge-LOW {
  background: #eafaf1;
  color: #1e8449;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.92rem;
}
th {
  text-align: left;
  padding: 10px 12px;
  border-bottom: 2px solid #e5e7eb;
  color: #555;
  font-weight: 600;
}
td {
  padding: 10px 12px;
  border-bottom: 1px solid #f0f0f0;
  vertical-align: top;
}
tr:hover td {
  background: #f8faff;
}

.btn {
  padding: 6px 14px;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 0.88rem;
  font-weight: 500;
}
.btn-primary {
  background: #4e8cff;
  color: #fff;
}
.btn-danger {
  background: #e74c3c;
  color: #fff;
}
.btn-sm {
  padding: 3px 10px;
  font-size: 0.82rem;
}

input,
select {
  padding: 6px 10px;
  border: 1px solid #d1d5db;
  border-radius: 5px;
  font-size: 0.9rem;
}
label {
  font-size: 0.88rem;
  color: #555;
  margin-bottom: 4px;
  display: block;
}
.filter-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: flex-end;
  margin-bottom: 18px;
}
.filter-group {
  display: flex;
  flex-direction: column;
}

.empty {
  color: #999;
  font-style: italic;
  padding: 24px 0;
  text-align: center;
}
.loading {
  color: #999;
  padding: 24px 0;
  text-align: center;
}
.error-msg {
  color: #c0392b;
  background: #fde8e8;
  padding: 10px 14px;
  border-radius: 6px;
  margin-bottom: 16px;
}
.mono {
  font-family: monospace;
  font-size: 0.85rem;
}
.pre-wrap {
  white-space: pre-wrap;
  word-break: break-all;
}
</style>

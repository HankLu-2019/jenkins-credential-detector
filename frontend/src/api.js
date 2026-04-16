import axios from "axios";

const http = axios.create({ baseURL: "/api" });

export const statsApi = {
  get: () => http.get("/stats/"),
};

export const findingsApi = {
  list: (params) => http.get("/findings/", { params }),
  get: (id) => http.get(`/findings/${id}`),
};

export const buildsApi = {
  list: (params) => http.get("/builds/", { params }),
  get: (id) => http.get(`/builds/${id}`),
};

export const exemptionsApi = {
  list: () => http.get("/exemptions/"),
  create: (body) => http.post("/exemptions/", body),
  createFromFinding: (findingId, reason, createdBy) =>
    http.post(`/exemptions/from-finding/${findingId}`, null, {
      params: { reason, created_by: createdBy },
    }),
  delete: (id) => http.delete(`/exemptions/${id}`),
};

import { create } from "zustand";

export interface ExaminerProfile {
  id: number;
  username: string;
  full_name: string;
  role: "admin" | "examiner";
}

interface LabState {
  token: string | null;
  examiner: ExaminerProfile | null;
  activeCaseId: number | null;
  activeDeviceId: number | null;
  activeAcquisitionId: number | null;
  setAuth: (token: string, examiner: ExaminerProfile) => void;
  logout: () => void;
  setActiveCaseId: (id: number | null) => void;
  setActiveDeviceId: (id: number | null) => void;
  setActiveAcquisitionId: (id: number | null) => void;
}

export const useLabStore = create<LabState>((set) => ({
  token: null,
  examiner: null,
  activeCaseId: null,
  activeDeviceId: null,
  activeAcquisitionId: null,
  setAuth: (token, examiner) => set({ token, examiner }),
  logout: () =>
    set({
      token: null,
      examiner: null,
      activeCaseId: null,
      activeDeviceId: null,
      activeAcquisitionId: null,
    }),
  setActiveCaseId: (activeCaseId) => set({ activeCaseId }),
  setActiveDeviceId: (activeDeviceId) => set({ activeDeviceId }),
  setActiveAcquisitionId: (activeAcquisitionId) => set({ activeAcquisitionId }),
}));


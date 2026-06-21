import { create } from 'zustand'

interface AppState {
  // Active import
  activeJobId: string | null
  setActiveJobId: (id: string | null) => void

  // Pantry badge — how many items in pantry
  pantryCount: number
  setPantryCount: (n: number) => void

  // UI
  sidebarOpen: boolean
  setSidebarOpen: (open: boolean) => void
}

export const useAppStore = create<AppState>((set) => ({
  activeJobId: null,
  setActiveJobId: (id) => set({ activeJobId: id }),

  pantryCount: 0,
  setPantryCount: (n) => set({ pantryCount: n }),

  sidebarOpen: false,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
}))

import { create } from 'zustand'

interface AppState {
  activeJobId: string | null
  setActiveJobId: (id: string | null) => void

  pantryCount: number
  setPantryCount: (n: number) => void
}

export const useAppStore = create<AppState>((set) => ({
  activeJobId: null,
  setActiveJobId: (id) => set({ activeJobId: id }),

  pantryCount: 0,
  setPantryCount: (n) => set({ pantryCount: n }),
}))

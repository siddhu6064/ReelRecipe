import { Tabs } from 'expo-router'
import { Ionicons } from '@expo/vector-icons'
import { useTranslation } from 'react-i18next'
import type { ComponentProps } from 'react'

type IoniconName = ComponentProps<typeof Ionicons>['name']

export default function TabsLayout() {
  const { t } = useTranslation()

  const TABS: { name: string; title: string; icon: IoniconName; activeIcon: IoniconName }[] = [
    { name: 'index',       title: t('nav.import'),      icon: 'add-circle-outline',    activeIcon: 'add-circle'      },
    { name: 'cookbook',    title: t('nav.cookbook'),    icon: 'book-outline',           activeIcon: 'book'            },
    { name: 'pantry',      title: t('nav.pantry'),      icon: 'basket-outline',         activeIcon: 'basket'          },
    { name: 'discover',    title: t('nav.discover'),    icon: 'sparkles-outline',       activeIcon: 'sparkles'        },
    { name: 'explore',     title: t('nav.explore'),     icon: 'globe-outline',          activeIcon: 'globe'           },
    { name: 'collections', title: t('nav.collections'), icon: 'folder-outline',         activeIcon: 'folder'          },
    { name: 'planner',     title: t('nav.planner'),     icon: 'calendar-outline',       activeIcon: 'calendar'        },
    { name: 'stats',       title: 'Stats',              icon: 'bar-chart-outline',      activeIcon: 'bar-chart'       },
    { name: 'profile',     title: t('nav.profile'),     icon: 'person-circle-outline',  activeIcon: 'person-circle'   },
  ]

  return (
    <Tabs
      screenOptions={{
        headerStyle:             { backgroundColor: '#0f0f0f' },
        headerTintColor:         '#f5f5f5',
        headerShadowVisible:     false,
        tabBarStyle:             { backgroundColor: '#0f0f0f', borderTopColor: '#1a1a1a', height: 84, paddingBottom: 24 },
        tabBarActiveTintColor:   '#ff6b35',
        tabBarInactiveTintColor: '#555',
        tabBarLabelStyle:        { fontSize: 9, fontWeight: '600' },
      }}
    >
      {TABS.map(tab => (
        <Tabs.Screen
          key={tab.name}
          name={tab.name}
          options={{
            title: tab.title,
            tabBarIcon: ({ color, focused }) => (
              <Ionicons name={focused ? tab.activeIcon : tab.icon} color={color} size={21} />
            ),
          }}
        />
      ))}
    </Tabs>
  )
}

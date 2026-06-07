<script setup lang="tsx">
import { useMagicKeys, whenever } from '@vueuse/core'
import {
	Avatar,
	Breadcrumbs,
	Dropdown,
	ListEmptyState,
	ListHeader,
	ListRows,
	ListSelectBanner,
	ListView,
} from 'frappe-ui'
import {
	Building2,
	ChevronDown,
	Eye,
	Folder,
	FolderPlus,
	Lock,
	MoreHorizontal,
	PlusIcon,
	SearchIcon,
	Shield,
} from 'lucide-vue-next'
import { computed, ref, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { wheneverChanges } from '../helpers'
import { confirmDialog } from '../helpers/confirm_dialog'
import session from '../session'
import { __ } from '../translation'
import { WorkbookListItem } from '../types/workbook.types'
import useUserStore from '../users/users'
import useWorkbook, { newWorkbookName } from './workbook'
import useWorkbookFolders, {
	buildFolderMoveOptions,
	childrenOf,
	folderBreadcrumb,
} from './workbookFolders'
import useWorkbooks from './workbooks'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const workbookStore = useWorkbooks()
const folderStore = useWorkbookFolders()

const isAdmin = computed(() => session.user.is_admin)

const scope = ref<'all' | 'owned' | 'shared'>('all')
// folder navigation is driven by the URL so the browser back button drills up a level
const currentFolder = computed(() => (route.query.folder as string) || null)
const searchQuery = ref('')

// workbooks of the current folder come from the server; subfolders + breadcrumb
// are derived on the client from the cached folder tree
async function refresh() {
	workbookStore.getWorkbooks(searchQuery.value, 0, scope.value, currentFolder.value || 'root')
}

wheneverChanges([scope, currentFolder], refresh, { immediate: true })
wheneverChanges(searchQuery, refresh, { debounce: 300 })

function drillInto(folder: string | null) {
	searchQuery.value = ''
	router.push({ query: folder ? { folder } : {} })
}

const subfolders = computed(() => childrenOf(folderStore.folders, currentFolder.value))

// ---- breadcrumbs (rendered in the navbar) ----
const breadcrumbs = computed(() => {
	const root = { label: __('Workbooks'), onClick: () => drillInto(null) }
	const trail = folderBreadcrumb(folderStore.folders, currentFolder.value).map((b) => ({
		label: b.title,
		onClick: () => drillInto(b.name),
	}))
	return [root, ...trail]
})

// ---- create workbook / folder ----
const creatingWorkbook = ref(false)
function openNewWorkbook() {
	creatingWorkbook.value = true
	const workbook = useWorkbook(newWorkbookName())
	workbook
		.insert()
		.then((doc) => router.push(`/workbook/${doc.name}`))
		.finally(() => (creatingWorkbook.value = false))
}

function openNewFolder() {
	confirmDialog({
		title: __('New Folder'),
		primaryActionLabel: __('Create'),
		fields: [
			{
				fieldname: 'title',
				label: __('Title'),
				placeholder: __('Folder name'),
				required: true,
			},
		],
		onSuccess: ({ values }: any) => {
			if (!values.title) return
			return folderStore.createFolder(values.title, currentFolder.value).then(refresh)
		},
	})
}

const newButtonOptions = computed(() => [
	{ label: __('New Folder'), icon: FolderPlus, onClick: openNewFolder },
])

// ---- folder actions ----
function renameFolder(folder: { name: string; title: string }) {
	confirmDialog({
		title: __('Rename Folder'),
		primaryActionLabel: __('Rename'),
		fields: [
			{
				fieldname: 'title',
				label: __('Title'),
				placeholder: folder.title,
				required: true,
			},
		],
		onSuccess: ({ values }: any) => {
			if (!values.title) return
			return folderStore.renameFolder(folder.name, values.title).then(refresh)
		},
	})
}

function deleteFolder(folder: { name: string; title: string }) {
	confirmDialog({
		title: __('Delete Folder'),
		message: __('Delete "{0}"? The folder must be empty first.', folder.title),
		theme: 'red',
		primaryActionLabel: __('Delete'),
		onSuccess: () => folderStore.deleteFolder(folder.name).then(refresh),
	})
}

async function moveWorkbook(workbook: string, folder: string | null) {
	await folderStore.moveWorkbookToFolder(workbook, folder)
	refresh()
}

// ---- bulk move (ListView selection) ----
// `selections` is a Set of row keys like "workbook:5" / "folder:3"
function selectedWorkbookNames(selections: Set<string>) {
	return [...selections]
		.filter((key) => key.startsWith('workbook:'))
		.map((key) => key.slice('workbook:'.length))
}

function bulkMoveOptions(selections: Set<string>, unselectAll: () => void) {
	return buildFolderMoveOptions(folderStore.folders, currentFolder.value, async (folder) => {
		const names = selectedWorkbookNames(selections)
		if (!names.length) return
		await folderStore.moveWorkbooksToFolder(names, folder)
		unselectAll()
		refresh()
	})
}

// ---- list columns (rows carry a __type discriminator: folder | workbook) ----
const columns = [
	{
		label: __('Title'),
		key: 'title',
		width: 4,
		prefix: (props: any) => {
			if (props.row.__type === 'folder') {
				return <Folder class="h-4 w-4 text-gray-600" stroke-width="1.5" />
			}
		},
	},
	{
		label: __('Access'),
		key: 'shared_with',
		width: 2,
		getLabel: (props: any) => {
			const row = props.row
			if (row.__type === 'folder') return ''
			if (row.shared_with_organization) return __('Everyone')
			if (!row.shared_with?.length) return __('Private')
			return row.shared_with.length > 1
				? `${row.shared_with.length} people`
				: userStore.getName(row.shared_with[0])
		},
		prefix: (props: any) => {
			const row = props.row as WorkbookListItem & { __type: string }
			if (row.__type === 'folder') return
			if (row.shared_with_organization) {
				return <Building2 class="h-3.5 w-3.5 text-blue-500" />
			}
			if (!row.shared_with?.length) {
				return <Lock class="h-3.5 w-3.5 text-orange-500" />
			}
			return <Shield class="h-3.5 w-3.5 text-green-500" />
		},
	},
	{
		label: __('Views'),
		key: 'views',
		width: 1.5,
		getLabel: () => {},
		prefix: (props: any) => {
			const row = props.row
			if (row.__type === 'folder') return
			return (
				<div class="flex gap-1">
					<Eye class="h-3.5 w-3.5 text-gray-600" stroke-width="1.5" />
					<span class="font-mono text-sm text-gray-700">{row.views}</span>
				</div>
			)
		},
	},
	{
		label: __('Owner'),
		key: 'owner',
		width: 2,
		getLabel: (props: any) => {
			const row = props.row
			if (row.__type === 'folder') return ''
			const user = userStore.getUser(row.owner)
			return user?.full_name || row.owner
		},
		prefix: (props: any) => {
			const row = props.row
			if (row.__type === 'folder') return
			const user = userStore.getUser(row.owner)
			return <Avatar size="md" label={row.owner} image={user?.user_image} />
		},
	},
	{
		label: __('Modified'),
		key: 'modified_from_now',
		width: 2,
		getLabel: (props: any) =>
			props.row.__type === 'folder' ? '' : props.row.modified_from_now,
	},
	{
		label: '',
		key: 'actions',
		width: 0.5,
		getLabel: () => {},
		prefix: (props: any) => {
			const row = props.row
			let options: any[] = []
			if (row.__type === 'folder') {
				if (!isAdmin.value) return
				options = [
					{ label: __('Rename'), icon: 'edit-2', onClick: () => renameFolder(row) },
					{
						label: __('Delete'),
						icon: 'trash-2',
						theme: 'red',
						onClick: () => deleteFolder(row),
					},
				]
			} else {
				options = [
					{
						group: __('Move to folder'),
						items: buildFolderMoveOptions(
							folderStore.folders,
							row.folder ?? null,
							(folder) => moveWorkbook(row.name, folder),
						),
					},
				]
			}
			return (
				<Dropdown options={options} placement="right">
					{{
						default: () => (
							<button
								class="flex h-7 w-7 items-center justify-center rounded hover:bg-gray-100"
								onClick={(e: Event) => e.stopPropagation()}
							>
								<MoreHorizontal class="h-4 w-4 text-gray-600" />
							</button>
						),
					}}
				</Dropdown>
			)
		},
	},
]

function onRowClick(row: any) {
	if (row.__type === 'folder') {
		drillInto(row.name)
	} else {
		router.push(`/workbook/${row.name}`)
	}
}

const rows = computed(() => {
	const folders = subfolders.value.map((f) => ({
		...f,
		__type: 'folder',
		_key: `folder:${f.name}`,
	}))
	const wbs = workbookStore.workbooks.map((w: WorkbookListItem) => ({
		...w,
		__type: 'workbook',
		_key: `workbook:${w.name}`,
	}))
	return [...folders, ...wbs]
})

const listOptions = computed(() => ({
	columns,
	rows: rows.value,
	rowKey: '_key',
	options: {
		showTooltip: false,
		onRowClick,
		emptyState: {
			title: currentFolder.value ? __('Empty Folder') : __('No Workbooks'),
			description: currentFolder.value
				? __('No folders or workbooks here.')
				: __('No workbooks to display.'),
			button:
				scope.value !== 'shared'
					? {
							label: __('New Workbook'),
							variant: 'solid',
							onClick: openNewWorkbook,
							loading: creatingWorkbook.value,
					  }
					: undefined,
		},
	},
}))

const keys = useMagicKeys()
const cmdV = keys['Meta+V']
whenever(cmdV, () => {
	if (!navigator.clipboard) return
	navigator.clipboard.readText().then((text) => {
		try {
			const json = JSON.parse(text)
			if (json.type === 'Workbook') {
				workbookStore.importWorkbook(json)
			}
		} catch (e) {}
	})
})

watchEffect(() => {
	document.title = 'Workbooks | Insights'
})
</script>

<template>
	<header class="flex h-12 items-center justify-between border-b py-2.5 pl-5 pr-2">
		<Breadcrumbs :items="breadcrumbs" />
		<div class="flex items-center gap-2">
			<div class="flex items-center">
				<Button
					:label="__('New Workbook')"
					variant="solid"
					@click="openNewWorkbook"
					:loading="creatingWorkbook"
					:class="isAdmin ? 'rounded-r-none' : ''"
				>
					<template #prefix>
						<PlusIcon class="w-4" />
					</template>
				</Button>
				<Dropdown v-if="isAdmin" :options="newButtonOptions" placement="right">
					<Button variant="solid" class="ml-px rounded-l-none px-1.5">
						<ChevronDown class="w-4" />
					</Button>
				</Dropdown>
			</div>
		</div>
	</header>

	<div class="mb-4 flex h-full flex-col gap-3 overflow-auto px-5 py-3">
		<div class="flex gap-2 overflow-visible py-1">
			<FormControl
				:placeholder="__('Search by Title')"
				v-model="searchQuery"
				:debounce="300"
				autocomplete="off"
			>
				<template #prefix>
					<SearchIcon class="h-4 w-4 text-gray-500" />
				</template>
			</FormControl>
			<FormControl
				type="select"
				v-model="scope"
				:options="[
					{ label: __('All'), value: 'all' },
					{ label: __('Created by me'), value: 'owned' },
					{ label: __('Shared with me'), value: 'shared' },
				]"
			/>
		</div>
		<ListView class="h-full" v-bind="listOptions">
			<ListHeader />
			<ListRows v-if="rows.length" />
			<ListEmptyState v-else />
			<ListSelectBanner>
				<template #actions="{ selections, unselectAll }">
					<Dropdown :options="bulkMoveOptions(selections, unselectAll)" placement="right">
						<Button :label="__('Move to folder')" variant="ghost">
							<template #prefix>
								<Folder class="h-4 w-4 text-gray-600" />
							</template>
						</Button>
					</Dropdown>
				</template>
			</ListSelectBanner>
		</ListView>
	</div>
</template>

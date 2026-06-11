import type { DataNode } from 'antd/es/tree';
import { FileMarkdownOutlined, LockOutlined, UserOutlined } from '@ant-design/icons';
import i18n from '@/locales/i18n';
import type { SkillInfo, SkillSource } from '@/api/types';

export const SYSTEM_ROOT_KEY = 'root:system';
export const PERSONAL_ROOT_KEY = 'root:personal';

export interface SkillTreeNode extends DataNode {
  nodeType: 'root' | 'category' | 'skill';
  source?: SkillSource;
  category?: string;
  label?: string;
  count?: number;
  skill?: SkillInfo;
  children?: SkillTreeNode[];
}

function groupByCategory(skills: SkillInfo[]): Map<string, SkillInfo[]> {
  const map = new Map<string, SkillInfo[]>();
  for (const skill of skills) {
    const category = skill.category || 'general';
    const bucket = map.get(category) ?? [];
    bucket.push(skill);
    map.set(category, bucket);
  }
  return map;
}

function buildCategoryNodes(
  source: SkillSource,
  grouped: Map<string, SkillInfo[]>
): SkillTreeNode[] {
  if (grouped.size === 0) {
    return [
      {
        key: `empty:${source}`,
        title: i18n.t('skills:emptyCategory'),
        label: i18n.t('skills:emptyCategory'),
        count: 0,
        nodeType: 'category',
        source,
        disabled: true,
        selectable: false,
        isLeaf: true,
      },
    ];
  }

  return Array.from(grouped.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([category, items]) => ({
      key: `category:${source}:${category}`,
      title: category,
      label: category,
      count: items.length,
      nodeType: 'category' as const,
      source,
      category,
      children: items
        .slice()
        .sort((a, b) => a.name.localeCompare(b.name))
        .map((skill) => ({
          key: `skill:${source}:${skill.skill_id}`,
          title: `${skill.name}.md`,
          label: `${skill.name}.md`,
          count: 1,
          nodeType: 'skill' as const,
          source,
          category,
          skill,
          isLeaf: true,
          icon: <FileMarkdownOutlined style={{ color: '#1677ff' }} />,
        })),
    }));
}

export function buildSkillTree(skills: SkillInfo[]): SkillTreeNode[] {
  const systemSkills = skills.filter((s) => s.source === 'system');
  const personalSkills = skills.filter((s) => s.source === 'personal');

  return [
    {
      key: SYSTEM_ROOT_KEY,
      title: i18n.t('skills:systemRootLabel'),
      label: i18n.t('skills:systemRootLabel'),
      count: systemSkills.length,
      nodeType: 'root',
      source: 'system',
      icon: <LockOutlined style={{ color: '#8c8c8c' }} />,
      children: buildCategoryNodes('system', groupByCategory(systemSkills)),
    },
    {
      key: PERSONAL_ROOT_KEY,
      title: i18n.t('skills:personalRootLabel'),
      label: i18n.t('skills:personalRootLabel'),
      count: personalSkills.length,
      nodeType: 'root',
      source: 'personal',
      icon: <UserOutlined style={{ color: '#52c41a' }} />,
      children: buildCategoryNodes('personal', groupByCategory(personalSkills)),
    },
  ];
}

export function findSkillNodeKey(skills: SkillInfo[], skillId: string): string | undefined {
  const skill = skills.find((s) => s.skill_id === skillId);
  if (!skill) return undefined;
  return `skill:${skill.source}:${skill.skill_id}`;
}

export function findFirstSkillNodeKey(tree: SkillTreeNode[]): string | undefined {
  for (const root of tree) {
    for (const category of root.children ?? []) {
      for (const leaf of category.children ?? []) {
        if (leaf.nodeType === 'skill') return String(leaf.key);
      }
    }
  }
  return undefined;
}

export function getDefaultExpandedKeys(tree: SkillTreeNode[]): string[] {
  const keys = [SYSTEM_ROOT_KEY, PERSONAL_ROOT_KEY];
  for (const root of tree) {
    for (const category of root.children ?? []) {
      if (category.nodeType === 'category' && category.children?.length) {
        keys.push(String(category.key));
      }
    }
  }
  return keys;
}

export function resolveSelectedCategory(
  tree: SkillTreeNode[],
  selectedKey?: string
): string {
  if (!selectedKey) return 'general';

  const findNode = (nodes: SkillTreeNode[]): SkillTreeNode | undefined => {
    for (const node of nodes) {
      if (node.key === selectedKey) return node;
      const child = findNode(node.children ?? []);
      if (child) return child;
    }
    return undefined;
  };

  const node = findNode(tree);
  if (!node) return 'general';
  if (node.nodeType === 'category') return node.category ?? 'general';
  if (node.nodeType === 'skill') return node.category ?? 'general';
  return 'general';
}

export function isPersonalContext(selectedKey?: string): boolean {
  return Boolean(selectedKey?.startsWith('root:personal') || selectedKey?.includes(':personal:'));
}

export function getSelectedPath(
  tree: SkillTreeNode[],
  selectedKey?: string
): string[] {
  if (!selectedKey) return [];

  const walk = (
    nodes: SkillTreeNode[],
    trail: string[]
  ): string[] | null => {
    for (const node of nodes) {
      const nextTrail = [...trail, node.label ?? String(node.title)];
      if (node.key === selectedKey) return nextTrail;
      const found = walk(node.children ?? [], nextTrail);
      if (found) return found;
    }
    return null;
  };

  return walk(tree, []) ?? [];
}

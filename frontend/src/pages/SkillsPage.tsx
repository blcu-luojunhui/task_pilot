import { useCallback, useEffect, useMemo, useState } from 'react';
import i18n from '@/locales/i18n';
import {
  Alert,
  Breadcrumb,
  Button,
  Card,
  Form,
  Input,
  Layout,
  Modal,
  Segmented,
  Select,
  Space,
  Spin,
  Typography,
  message,
  theme,
} from 'antd';
import {
  DownOutlined,
  FileMarkdownOutlined,
  FolderOutlined,
  PlusOutlined,
  ReloadOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { useLocation } from 'react-router-dom';
import {
  createPersonalSkill,
  createSystemSkill,
  deletePersonalSkill,
  deleteSystemSkill,
  listSkills,
  updatePersonalSkill,
  updateSystemSkill,
} from '@/api/skills';
import { useAuthStore } from '@/stores/authStore';
import type { SkillInfo } from '@/api/types';
import { SkillCallHistoryDrawer } from '@/components/skill/SkillCallHistoryDrawer';
import { SkillMarkdownPanel } from '@/components/skill/SkillMarkdownPanel';
import { EmptyState } from '@/components/common/EmptyState';
import {
  PERSONAL_ROOT_KEY,
  buildSkillTree,
  findSkillNodeKey,
  getSelectedPath,
  resolveSelectedCategory,
} from '@/utils/skillTree';
import { useTranslation } from 'react-i18next';
import './SkillsPage.css';

const { Sider, Content } = Layout;

type CategoryGroup = {
  key: string;
  name: string;
  count: number;
  categories: Array<{
    key: string;
    name: string;
    count: number;
    skills: SkillInfo[];
  }>;
};

interface CreateSkillFormValues {
  name: string;
  description: string;
  category: string;
  scope: string;
  target: 'personal' | 'system';
  skill_type: 'knowledge';
  detail: string;
  guidelines: string;
}

const CATEGORY_OPTIONS = [
  'chat_ops',
  'database',
  'http',
  'task',
  'utils',
  'general',
].map((value) => ({ label: value, value }));

function buildSkillMarkdown(values: CreateSkillFormValues): string {
  const lines = values.guidelines
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => `- ${line}`);

  return [
    '---',
    `name: ${values.name.trim()}`,
    `description: ${values.description.trim().replace(/\n+/g, ' ')}`,
    `category: ${values.category.trim() || 'chat_ops'}`,
    `skill_type: ${values.skill_type}`,
    `scope: ${values.scope.trim() || 'agent:*'}`,
    '---',
    '',
    '## Description',
    '',
    values.detail.trim() || i18n.t('skills:formDetailDefault'),
    '',
    '## Guidelines',
    '',
    ...lines,
    '',
  ].join('\n');
}

export function SkillsPage() {
  const { t } = useTranslation('skills');
  const location = useLocation();
  const { token } = theme.useToken();
  const account = useAuthStore((s) => s.account);
  const isAdmin = account?.role === 'admin';
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string>();
  const [expandedKeys, setExpandedKeys] = useState<string[]>([]);
  const [draft, setDraft] = useState('');
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [treeSearch, setTreeSearch] = useState('');
  const [sourceView, setSourceView] = useState<'system' | 'personal'>('system');
  const [drawerSkill, setDrawerSkill] = useState<SkillInfo | null>(null);
  const [createForm] = Form.useForm<CreateSkillFormValues>();

  const searchedSkills = useMemo(() => {
    const keyword = treeSearch.trim().toLowerCase();
    if (!keyword) return skills;
    return skills.filter((skill) => {
      const haystack = [
        skill.name,
        skill.category,
        skill.description,
        skill.source,
        skill.skill_type,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(keyword);
    });
  }, [skills, treeSearch]);

  const filteredSkills = useMemo(
    () => searchedSkills.filter((skill) => skill.source === sourceView),
    [searchedSkills, sourceView]
  );

  const treeData = useMemo(() => buildSkillTree(skills), [skills]);
  const categoryGroups = useMemo<CategoryGroup[]>(() => {
    const categoryMap = new Map<string, SkillInfo[]>();
    for (const skill of filteredSkills) {
      const category = skill.category || 'general';
      categoryMap.set(category, [...(categoryMap.get(category) ?? []), skill]);
    }
    return Array.from(categoryMap.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([name, items]) => ({
        key: `category:${sourceView}:${name}`,
        name,
        count: items.length,
        categories: [
          {
            key: `category:${sourceView}:${name}`,
            name,
            count: items.length,
            skills: items.slice().sort((a, b) => a.name.localeCompare(b.name)),
          },
        ],
      }));
  }, [filteredSkills, sourceView]);
  const systemCount = useMemo(() => skills.filter((s) => s.source === 'system').length, [skills]);
  const personalCount = useMemo(() => skills.filter((s) => s.source === 'personal').length, [skills]);
  const breadcrumb = useMemo(
    () => getSelectedPath(treeData, selectedKey),
    [treeData, selectedKey]
  );

  const selectedSkill = useMemo(() => {
    if (!selectedKey?.startsWith('skill:')) return null;
    const parts = selectedKey.split(':');
    const skillId = parts.slice(2).join(':');
    return skills.find((s) => s.skill_id === skillId) ?? null;
  }, [selectedKey, skills]);

  const normalizeSkills = useCallback(
    (data: SkillInfo[]) =>
      data.map((skill) => ({
        ...skill,
        source: skill.source ?? 'system',
        editable: skill.editable ?? (skill.source === 'personal' || (isAdmin && skill.source === 'system')),
        markdown: skill.markdown ?? '',
        parameters: skill.parameters ?? {},
      })),
    [isAdmin]
  );

  const load = useCallback(async (cancelled: () => boolean, autoSelect = false) => {
    setLoading(true);
    setError(null);
    try {
      const data = await listSkills();
      if (cancelled()) return;
      const normalized = normalizeSkills(Array.isArray(data) ? data : []);
      setSkills(normalized);
      if (expandedKeys.length === 0) {
        const defaults = Array.from(
          new Set(
            normalized
              .filter((skill) => skill.source === sourceView)
              .map((skill) => `category:${sourceView}:${skill.category || 'general'}`)
          )
        );
        setExpandedKeys(defaults);
      }
      if (autoSelect && !selectedKey) {
        setSelectedKey(undefined);
      }
    } catch (err) {
      if (cancelled()) return;
      setSkills([]);
      setError(err instanceof Error ? err.message : t('loadFailed'));
    } finally {
      if (!cancelled()) setLoading(false);
    }
  }, [expandedKeys.length, normalizeSkills, selectedKey, sourceView]);

  useEffect(() => {
    let stale = false;
    void load(() => stale, true);
    return () => {
      stale = true;
    };
  }, [location.key]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (selectedSkill) {
      setDraft(selectedSkill.markdown);
      setDirty(false);
    }
  }, [selectedSkill]);

  useEffect(() => {
    if (treeSearch.trim()) {
      const keys = Array.from(
        new Set(
          filteredSkills.map((skill) => `category:${sourceView}:${skill.category || 'general'}`)
        )
      );
      setExpandedKeys(keys);
    }
  }, [filteredSkills, sourceView, treeSearch]);

  useEffect(() => {
    const keys = Array.from(
      new Set(
        skills
          .filter((skill) => skill.source === sourceView)
          .map((skill) => `category:${sourceView}:${skill.category || 'general'}`)
      )
    );
    setExpandedKeys(keys);
  }, [skills, sourceView]);

  useEffect(() => {
    if (!selectedKey?.startsWith('skill:')) return;
    if (selectedSkill && selectedSkill.source !== sourceView) {
      setSelectedKey(undefined);
    }
  }, [selectedKey, selectedSkill, sourceView]);

  const toggleExpanded = (key: string) => {
    setExpandedKeys((prev) =>
      prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key]
    );
  };

  const isExpanded = (key: string) => expandedKeys.includes(key);

  const handleSelect = (key: string) => {
    if (!key || !key.startsWith('skill:')) {
      if (key) setSelectedKey(key);
      return;
    }

    if (dirty && selectedSkill?.editable) {
      Modal.confirm({
        title: t('unsavedTitle'),
        content: t('unsavedContent'),
        okText: t('continueAnyway'),
        cancelText: t('cancel'),
        onOk: () => {
          setSelectedKey(key);
          setDirty(false);
        },
      });
      return;
    }

    setSelectedKey(key);
  };

  const openCreateModal = () => {
    const selectedCategory = resolveSelectedCategory(treeData, selectedKey);
    const category =
      selectedCategory && selectedCategory !== 'general' ? selectedCategory : 'chat_ops';
    createForm.setFieldsValue({
      name: 'new-skill',
      description: t('formDescriptionPlaceholder'),
      category,
      scope: 'agent:*',
      skill_type: 'knowledge',
      detail: t('formDetailDefault'),
      guidelines: '',
    });
    setCreateOpen(true);
  };

  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields();
      setCreateSubmitting(true);
      const markdown = buildSkillMarkdown(values);
      const created =
        values.target === 'system'
          ? await createSystemSkill(markdown)
          : await createPersonalSkill(markdown);
      const refreshed = normalizeSkills(await listSkills());
      setSkills(refreshed);
      const targetSource = values.target === 'system' ? 'system' : 'personal';
      setSourceView(targetSource as 'system' | 'personal');
      const keys = Array.from(
        new Set(
          refreshed
            .filter((skill) => skill.source === targetSource)
            .map((skill) => `category:${targetSource}:${skill.category || 'general'}`)
        )
      );
      setExpandedKeys(keys);
      setSelectedKey(findSkillNodeKey(refreshed, created.skill_id));
      setCreateOpen(false);
      createForm.resetFields();
      message.success(t('created'));
    } catch (err) {
      if (err instanceof Error) {
        message.error(err.message || t('createFailed'));
      }
    } finally {
      setCreateSubmitting(false);
    }
  };

  const handleSave = async () => {
    if (!selectedSkill) {
      message.warning(t('selectOneFirst'));
      return;
    }
    if (!selectedSkill.editable) {
      message.warning(t('readOnly'));
      return;
    }

    setSaving(true);
    try {
      const updated =
        selectedSkill.source === 'system'
          ? await updateSystemSkill(selectedSkill.skill_id, draft)
          : await updatePersonalSkill(selectedSkill.skill_id, draft);
      message.success(t('saved'));
      setDirty(false);
      const normalized = normalizeSkills(await listSkills());
      setSkills(normalized);
      setSelectedKey(findSkillNodeKey(normalized, updated.skill_id));
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = () => {
    if (!selectedSkill || !selectedSkill.editable) return;
    Modal.confirm({
      title: t('deleteConfirmTitle', { name: selectedSkill.name }),
      content: t('deleteConfirmContent'),
      okText: t('delete'),
      okButtonProps: { danger: true },
      cancelText: t('cancel'),
      onOk: async () => {
        try {
          if (selectedSkill.source === 'system') {
            await deleteSystemSkill(selectedSkill.skill_id);
          } else {
            await deletePersonalSkill(selectedSkill.skill_id);
          }
          message.success(t('deleted'));
          setSelectedKey(selectedSkill.source === 'system' ? 'root:system' : PERSONAL_ROOT_KEY);
          setDirty(false);
          await load(() => false, false);
        } catch (err) {
          message.error(err instanceof Error ? err.message : t('deleteFailed'));
        }
      },
    });
  };

  const editing = selectedSkill?.editable === true;

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        variant="borderless"
        styles={{ body: { padding: '14px 18px' } }}
        style={{ boxShadow: '0 1px 2px rgba(0, 0, 0, 0.03)' }}
      >
        <Space align="center" style={{ width: '100%', justifyContent: 'space-between' }}>
          <div>
            <Typography.Title level={4} style={{ margin: 0 }}>
              {t('title')}
            </Typography.Title>
            <Typography.Text type="secondary">
              {t('subtitle')}
            </Typography.Text>
          </div>
          <Space>
            <Typography.Text type="secondary">
              {t('countLabel', { system: systemCount, personal: personalCount })}
            </Typography.Text>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
              {t('createButton')}
            </Button>
            <Button icon={<ReloadOutlined />} onClick={() => void load(() => false, false)} loading={loading}>
              {t('refresh')}
            </Button>
          </Space>
        </Space>
      </Card>

      {error && (
        <Alert
          type="error"
          showIcon
          message={t('loadFailedTitle')}
          description={error}
          action={
            <Button size="small" onClick={() => void load(() => false, false)}>
              {t('retry')}
            </Button>
          }
        />
      )}

      {loading && skills.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin />
        </div>
      ) : skills.length === 0 ? (
        <EmptyState description={t('emptyHint')} />
      ) : (
        <Layout
          style={{
            background: token.colorBgLayout,
            border: `1px solid ${token.colorBorderSecondary}`,
            borderRadius: token.borderRadius,
            overflow: 'hidden',
            minHeight: 620,
          }}
        >
          <Sider
            width={248}
            theme="light"
            style={{
              background: token.colorBgContainer,
              borderRight: `1px solid ${token.colorBorderSecondary}`,
              padding: 10,
            }}
          >
            <Space direction="vertical" size={8} style={{ width: '100%', marginBottom: 10 }}>
              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Typography.Text strong style={{ fontSize: 14 }}>
                  {t('fileTree')}
                </Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {filteredSkills.length}
                </Typography.Text>
              </Space>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t('treeHint')}
              </Typography.Text>
            </Space>
            <Input.Search
              allowClear
              size="small"
              placeholder={t('searchPlaceholder')}
              value={treeSearch}
              onChange={(event) => setTreeSearch(event.target.value)}
              style={{ marginBottom: 12 }}
            />
            <Segmented
              block
              size="small"
              value={sourceView}
              options={[
                { label: `${t('systemRootLabel').split(' ')[0]} ${systemCount}`, value: 'system' },
                { label: `${t('personalRootLabel').split(' ')[0]} ${personalCount}`, value: 'personal' },
              ]}
              onChange={(value) => setSourceView(value as 'system' | 'personal')}
              style={{ marginBottom: 10 }}
            />
            <div className="skill-explorer">
              {categoryGroups.length === 0 ? (
                <div className="skill-explorer-empty">{t('noFiles')}</div>
              ) : (
                categoryGroups.map((group) =>
                  group.categories.map((category) => {
                    const categoryOpen = isExpanded(category.key);
                    return (
                      <div className="skill-explorer-category" key={category.key}>
                        <button
                          className={[
                            'skill-explorer-categoryButton',
                            selectedKey === category.key ? 'is-selected' : '',
                          ].join(' ')}
                          type="button"
                          onClick={() => {
                            toggleExpanded(category.key);
                            handleSelect(category.key);
                          }}
                        >
                          <span className="skill-explorer-caret">
                            {categoryOpen ? <DownOutlined /> : <RightOutlined />}
                          </span>
                          <FolderOutlined className="skill-explorer-folderIcon" />
                          <span className="skill-explorer-categoryTitle">{category.name}</span>
                          <span className="skill-explorer-count">{category.count}</span>
                        </button>

                        {categoryOpen && (
                          <div className="skill-explorer-files">
                            {category.skills.map((skill) => {
                              const key = `skill:${skill.source}:${skill.skill_id}`;
                              const selected = selectedKey === key;
                              return (
                                <button
                                  className={[
                                    'skill-explorer-fileButton',
                                    selected ? 'is-selected' : '',
                                  ].join(' ')}
                                  type="button"
                                  title={`${skill.name}.md`}
                                  key={key}
                                  onClick={() => handleSelect(key)}
                                >
                                  <FileMarkdownOutlined className="skill-explorer-fileIcon" />
                                  <span className="skill-explorer-fileName">
                                    <span className="skill-explorer-fileStem">{skill.name}</span>
                                    <span className="skill-explorer-fileExt">.md</span>
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })
                )
              )}
            </div>
          </Sider>
          <Content style={{ padding: 16, minHeight: 620, display: 'flex', flexDirection: 'column' }}>
            {breadcrumb.length > 0 && (
              <Breadcrumb
                style={{ marginBottom: 12 }}
                items={breadcrumb.map((label) => ({ title: label }))}
              />
            )}
            <SkillMarkdownPanel
              skill={selectedSkill}
              draft={draft}
              editing={editing}
              dirty={dirty}
              saving={saving}
              onDraftChange={(value) => {
                setDraft(value);
                setDirty(true);
              }}
              onSave={() => void handleSave()}
              onDelete={handleDelete}
              onShowCalls={
                selectedSkill?.source === 'system'
                  ? () => setDrawerSkill(selectedSkill)
                  : undefined
              }
            />
          </Content>
        </Layout>
      )}

      <Modal
        title={t('createModalTitle')}
        open={createOpen}
        okText={t('createModalOk')}
        cancelText={t('createModalCancel')}
        confirmLoading={createSubmitting}
        onOk={() => void handleCreate()}
        onCancel={() => {
          setCreateOpen(false);
          createForm.resetFields();
        }}
      >
        <Form<CreateSkillFormValues> layout="vertical" form={createForm}>
          <Form.Item
            label={t('formSkillName')}
            name="name"
            rules={[
              { required: true, message: t('formSkillNameRequired') },
              { max: 128, message: t('formSkillNameMax') },
            ]}
          >
            <Input placeholder={t('formSkillNamePlaceholder')} />
          </Form.Item>
          <Form.Item
            label={t('formDescription')}
            name="description"
            rules={[{ required: true, message: t('formDescriptionRequired') }]}
          >
            <Input placeholder={t('formDescriptionPlaceholder')} />
          </Form.Item>
          <Space style={{ width: '100%' }} size={12}>
            <Form.Item
              label="Category"
              name="category"
              style={{ flex: 1 }}
              rules={[{ required: true, message: t('formCategoryRequired') }]}
            >
              <Select showSearch options={CATEGORY_OPTIONS} />
            </Form.Item>
            <Form.Item label="Skill Type" name="skill_type" style={{ width: 140 }}>
              <Select options={[{ label: 'knowledge', value: 'knowledge' }]} disabled />
            </Form.Item>
          </Space>
          <Form.Item
            label="Scope"
            name="scope"
            rules={[{ required: true, message: t('formScopeRequired') }]}
          >
            <Input placeholder="agent:*" />
          </Form.Item>
          {isAdmin && (
            <Form.Item
              label={t('formTarget')}
              name="target"
              initialValue="personal"
              rules={[{ required: true }]}
            >
              <Select
                options={[
                  { label: t('formTargetPersonal'), value: 'personal' },
                  { label: t('formTargetSystem'), value: 'system' },
                ]}
              />
            </Form.Item>
          )}
          <Form.Item
            label={t('formDetail')}
            name="detail"
            rules={[{ required: true, message: t('formDetailRequired') }]}
          >
            <Input.TextArea autoSize={{ minRows: 3, maxRows: 6 }} />
          </Form.Item>
          <Form.Item
            label={t('formGuidelines')}
            name="guidelines"
          >
            <Input.TextArea autoSize={{ minRows: 3, maxRows: 8 }} placeholder={t('formGuidelinesPlaceholder')} />
          </Form.Item>
        </Form>
      </Modal>

      <SkillCallHistoryDrawer
        skill={drawerSkill}
        open={drawerSkill !== null}
        onClose={() => setDrawerSkill(null)}
      />
    </Space>
  );
}

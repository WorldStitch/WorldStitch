import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import SectionHeader from '@/components/SectionHeader';
import Card from '@/components/Card';
import Button from '@/components/Button';
import Input from '@/components/Input';
import { groups, users } from '@/api';

const MIN_GROUP_NAME_LENGTH = 2;

export default function OwnerGroups() {
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selectedGroupId, setSelectedGroupId] = useState(null);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [selectedRole, setSelectedRole] = useState('member');
  const [groupName, setGroupName] = useState('');
  const [groupDescription, setGroupDescription] = useState('');

  const { data: groupList = [] } = useQuery({ queryKey: ['groups'], queryFn: groups.list });
  const { data: userList = [] } = useQuery({ queryKey: ['users'], queryFn: users.list });
  const selectedGroup = useMemo(
    () => groupList.find((group) => group.id === selectedGroupId) || null,
    [groupList, selectedGroupId]
  );

  useEffect(() => {
    setGroupName(selectedGroup?.name || '');
    setGroupDescription(selectedGroup?.description || '');
  }, [selectedGroup]);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['groups'] });
    qc.invalidateQueries({ queryKey: ['users'] });
  };

  const createGroup = useMutation({
    mutationFn: () => groups.create({ name: name.trim(), description: description.trim() || undefined }),
    onSuccess: (group) => {
      setName('');
      setDescription('');
      setSelectedGroupId(group.id);
      refresh();
      toast.success('Group created');
    },
    onError: (err) => toast.error(err.message),
  });

  const renameGroup = useMutation({
    mutationFn: ({ id, payload }) => groups.update(id, payload),
    onSuccess: () => {
      refresh();
      toast.success('Group updated');
    },
    onError: (err) => toast.error(err.message),
  });

  const deleteGroup = useMutation({
    mutationFn: groups.remove,
    onSuccess: () => {
      setSelectedGroupId(null);
      refresh();
      toast.success('Group deleted');
    },
    onError: (err) => toast.error(err.message),
  });

  const addMember = useMutation({
    mutationFn: () => groups.addMember(selectedGroupId, selectedUserId, selectedRole),
    onSuccess: () => {
      refresh();
      toast.success('Member added');
    },
    onError: (err) => toast.error(err.message),
  });

  const removeMember = useMutation({
    mutationFn: ({ groupId, userId }) => groups.removeMember(groupId, userId),
    onSuccess: () => {
      refresh();
      toast.success('Member removed');
    },
    onError: (err) => toast.error(err.message),
  });

  return (
    <div className="p-10 space-y-6">
      <SectionHeader title="🛡️ Groups" subtitle="Create groups, manage members, and prepare shared vault access." />
      <div className="grid lg:grid-cols-[320px,1fr] gap-6">
        <Card className="p-6 space-y-4">
          <Input label="Group name" value={name} onChange={(e) => setName(e.target.value)} />
          <Input label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
          <Button onClick={() => createGroup.mutate()} disabled={name.trim().length < MIN_GROUP_NAME_LENGTH}>Create group</Button>
          <div className="space-y-2 pt-2 border-t border-border-subtle">
            {groupList.map((group) => (
              <button
                key={group.id}
                onClick={() => setSelectedGroupId(group.id)}
                className={`w-full text-left rounded-xl px-4 py-3 ${selectedGroupId === group.id ? 'bg-accent-soft text-accent' : 'bg-elevated text-txt'}`}
              >
                <div className="font-semibold">{group.name}</div>
                <div className="text-xs text-txt-muted">{group.members.length} members</div>
              </button>
            ))}
          </div>
        </Card>

        <Card className="p-6 space-y-4">
          {!selectedGroup ? (
            <p className="text-txt-muted">Select a group to manage members.</p>
          ) : (
            <>
              <div className="flex flex-wrap gap-3 items-end">
                <div className="flex-1 min-w-[220px]">
                  <Input
                    label="Rename group"
                    value={groupName}
                    onChange={(e) => setGroupName(e.target.value)}
                  />
                </div>
                <Button variant="secondary" onClick={() => renameGroup.mutate({ id: selectedGroup.id, payload: { name: groupName, description: groupDescription } })}>
                  Save
                </Button>
                <Button variant="danger" onClick={() => deleteGroup.mutate(selectedGroup.id)}>Delete group</Button>
              </div>
              <Input label="Description" value={groupDescription} onChange={(e) => setGroupDescription(e.target.value)} />

              <div className="grid md:grid-cols-[1fr,160px,120px] gap-3 items-end">
                <div>
                  <label className="block text-txt-muted text-sm mb-1.5 font-medium">Add member</label>
                  <select
                    value={selectedUserId}
                    onChange={(e) => setSelectedUserId(e.target.value)}
                    className="w-full bg-elevated rounded-xl px-4 py-3 text-txt border-2 border-transparent focus:border-accent focus:outline-none"
                  >
                    <option value="">Select user</option>
                    {userList.map((user) => (
                      <option key={user.id} value={user.id}>{user.username}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-txt-muted text-sm mb-1.5 font-medium">Role</label>
                  <select
                    value={selectedRole}
                    onChange={(e) => setSelectedRole(e.target.value)}
                    className="w-full bg-elevated rounded-xl px-4 py-3 text-txt border-2 border-transparent focus:border-accent focus:outline-none"
                  >
                    <option value="member">member</option>
                    <option value="observer">observer</option>
                    <option value="gm">gm</option>
                  </select>
                </div>
                <Button onClick={() => addMember.mutate()} disabled={!selectedUserId}>Add</Button>
              </div>

              <div className="space-y-2 pt-3 border-t border-border-subtle">
                {selectedGroup.members.map((memberId) => {
                  const user = userList.find((item) => item.id === memberId);
                  return (
                    <div key={memberId} className="flex items-center gap-3 bg-elevated rounded-xl px-4 py-3">
                      <div className="flex-1">
                        <div className="font-medium text-txt">{user?.username || memberId}</div>
                        <div className="text-xs text-txt-muted">{selectedGroup.member_roles?.[memberId] || 'member'}</div>
                      </div>
                      <Button variant="danger" size="sm" onClick={() => removeMember.mutate({ groupId: selectedGroup.id, userId: memberId })}>
                        Remove
                      </Button>
                    </div>
                  );
                })}
                {!selectedGroup.members.length && <p className="text-sm text-txt-muted">No members yet.</p>}
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

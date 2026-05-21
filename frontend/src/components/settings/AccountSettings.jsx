import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { toast } from 'sonner';
import Button from '@/components/Button';
import Input from '@/components/Input';
import { auth } from '@/api';
import { changePasswordSchema } from '@/schemas/auth';

export default function AccountSettings({ user }) {
  const [showPassword, setShowPassword] = useState(false);

  const getUserRole = (u) => {
    if (u?.roles && Array.isArray(u.roles)) return u.roles[0] || 'member';
    return u?.role || 'member';
  };

  const { register, handleSubmit, formState: { errors }, reset } = useForm({
    resolver: zodResolver(changePasswordSchema),
  });

  const onChangePassword = handleSubmit(async ({ currentPassword, newPassword }) => {
    try {
      await auth.changePassword(currentPassword, newPassword);
      reset();
      toast.success('Password updated successfully');
    } catch (err) {
      toast.error(err.message || 'Failed to update password');
    }
  });

  const FieldError = ({ message }) =>
    message ? <p className="text-danger text-xs mt-1">{message}</p> : null;

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-bold text-txt mb-4">Account Info</h3>
        <div className="space-y-4 bg-elevated rounded-lg p-4">
          <div>
            <p className="text-txt-muted text-sm">Username</p>
            <p className="text-txt font-medium">{user?.username || 'N/A'}</p>
          </div>
          <div>
            <p className="text-txt-muted text-sm">Email</p>
            <p className="text-txt font-medium">{user?.email || 'N/A'}</p>
          </div>
          <div>
            <p className="text-txt-muted text-sm">Role</p>
            <p className="text-txt font-medium capitalize">{getUserRole(user)}</p>
          </div>
        </div>
      </div>

      <div className="border-t border-txt-muted/20 pt-6">
        <h3 className="text-lg font-bold text-txt mb-4">Change Password</h3>
        <form onSubmit={onChangePassword} className="space-y-4">
          <div>
            <Input label="Current Password" type="password" placeholder="••••••••" {...register('currentPassword')} />
            <FieldError message={errors.currentPassword?.message} />
          </div>
          <div>
            <Input label="New Password" type={showPassword ? 'text' : 'password'} placeholder="••••••••" {...register('newPassword')} />
            <FieldError message={errors.newPassword?.message} />
          </div>
          <div>
            <Input label="Confirm Password" type={showPassword ? 'text' : 'password'} placeholder="••••••••" {...register('confirmPassword')} />
            <FieldError message={errors.confirmPassword?.message} />
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={showPassword}
              onChange={(e) => setShowPassword(e.target.checked)}
              className="w-4 h-4 rounded bg-elevated border-2 border-txt-muted accent-accent"
            />
            <span className="text-txt-secondary text-sm">Show password</span>
          </label>
          <Button type="submit" variant="success" className="w-full">Update Password</Button>
        </form>
      </div>
    </div>
  );
}

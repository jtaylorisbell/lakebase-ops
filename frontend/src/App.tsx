import { useState } from 'react';
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Plus,
  CheckCircle2,
  Circle,
  ListTodo,
  Trash2,
  ChevronDown,
  User,
  Database,
  Sparkles,
  BarChart3,
  Flag,
  Calendar,
} from 'lucide-react';
import { format, formatDistanceToNow, isPast, isToday } from 'date-fns';
import { api } from './api/client';
import type { CreateTodoRequest, Priority, Todo } from './types/api';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 2000,
      retry: 1,
    },
  },
});

type FilterMode = 'all' | 'active' | 'completed';

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const PRIORITY_DOT_CLASSES: Record<Priority, string> = {
  high: 'priority-dot-high',
  medium: 'priority-dot-medium',
  low: 'priority-dot-low',
};

const PRIORITY_BADGE_CLASSES: Record<Priority, string> = {
  high: 'bg-[var(--accent-danger-dim)] text-[var(--accent-danger)]',
  medium: 'bg-[var(--accent-warning-dim)] text-[var(--accent-warning)]',
  low: 'bg-[var(--bg-elevated)] text-[var(--text-muted)]',
};

const PRIORITY_ACTIVE_CLASSES: Record<Priority, string> = {
  high: 'bg-[var(--accent-danger)] text-white',
  medium: 'bg-[var(--accent-warning)] text-white',
  low: 'bg-[var(--text-muted)] text-white',
};

function useInvalidateTodos() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ['todos'] });
    qc.invalidateQueries({ queryKey: ['stats'] });
  };
}

function TodoItem({ todo }: { todo: Todo }) {
  const invalidate = useInvalidateTodos();

  const toggleMutation = useMutation({
    mutationFn: () => api.toggleTodo(todo.id),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteTodo(todo.id),
    onSuccess: invalidate,
  });

  const completedStyle = todo.completed ? 'line-through text-[var(--text-muted)]' : '';

  return (
    <div className={`card group px-5 py-4 flex items-start gap-4 animate-fade-in-up ${
      todo.completed ? 'opacity-60' : ''
    }`}>
      <button
        onClick={() => toggleMutation.mutate()}
        className="mt-0.5 flex-shrink-0"
        disabled={toggleMutation.isPending}
      >
        {todo.completed ? (
          <CheckCircle2 className="h-6 w-6 text-[var(--accent-success)] animate-check" />
        ) : (
          <Circle className="h-6 w-6 text-[var(--border-hover)] hover:text-[var(--accent-primary)]" />
        )}
      </button>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={`priority-dot ${PRIORITY_DOT_CLASSES[todo.priority]}`} />
          <h3 className={`text-base font-medium ${completedStyle || 'text-[var(--text-primary)]'}`}>
            {todo.title}
          </h3>
        </div>
        {todo.description && (
          <p className={`mt-1 text-sm ${completedStyle || 'text-[var(--text-secondary)]'}`}>
            {todo.description}
          </p>
        )}
        <div className="mt-2 flex items-center gap-3 text-xs text-[var(--text-muted)]">
          <span>{formatDistanceToNow(new Date(todo.created_at), { addSuffix: true })}</span>
          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${PRIORITY_BADGE_CLASSES[todo.priority]}`}>
            {capitalize(todo.priority)}
          </span>
          {todo.due_date && (
            <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
              todo.completed
                ? 'bg-[var(--bg-elevated)] text-[var(--text-muted)]'
                : isPast(new Date(todo.due_date + 'T00:00:00')) && !isToday(new Date(todo.due_date + 'T00:00:00'))
                  ? 'bg-[var(--accent-danger-dim)] text-[var(--accent-danger)]'
                  : isToday(new Date(todo.due_date + 'T00:00:00'))
                    ? 'bg-[var(--accent-warning-dim)] text-[var(--accent-warning)]'
                    : 'bg-[var(--bg-elevated)] text-[var(--text-muted)]'
            }`}>
              <Calendar className="h-3 w-3" />
              {format(new Date(todo.due_date + 'T00:00:00'), 'MMM d')}
            </span>
          )}
        </div>
      </div>

      <button
        onClick={() => deleteMutation.mutate()}
        className="opacity-0 group-hover:opacity-100 p-2 rounded-lg hover:bg-[var(--accent-danger-dim)] text-[var(--text-muted)] hover:text-[var(--accent-danger)]"
        disabled={deleteMutation.isPending}
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  );
}

function AddTodoForm() {
  const invalidate = useInvalidateTodos();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<Priority>('medium');
  const [dueDate, setDueDate] = useState('');
  const [showDetails, setShowDetails] = useState(false);

  const createMutation = useMutation({
    mutationFn: (data: CreateTodoRequest) => api.createTodo(data),
    onSuccess: () => {
      invalidate();
      setTitle('');
      setDescription('');
      setPriority('medium');
      setDueDate('');
      setShowDetails(false);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    createMutation.mutate({
      title: title.trim(),
      description: description.trim() || undefined,
      priority,
      due_date: dueDate || undefined,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="card p-5">
      <div className="flex items-center gap-3">
        <Plus className="h-5 w-5 text-[var(--accent-primary)] flex-shrink-0" />
        <input
          type="text"
          placeholder="What needs to be done?"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="flex-1 border-none bg-transparent text-base font-medium placeholder:text-[var(--text-muted)] focus:ring-0 focus:shadow-none p-0"
          style={{ boxShadow: 'none' }}
        />
        <button
          type="button"
          onClick={() => setShowDetails(!showDetails)}
          className={`p-2 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)] ${showDetails ? 'bg-[var(--bg-elevated)]' : ''}`}
        >
          <ChevronDown className={`h-4 w-4 transition-transform ${showDetails ? 'rotate-180' : ''}`} />
        </button>
        <button
          type="submit"
          disabled={!title.trim() || createMutation.isPending}
          className="btn-primary px-4 py-2 text-sm disabled:opacity-40 disabled:cursor-not-allowed disabled:transform-none"
        >
          Add
        </button>
      </div>

      {showDetails && (
        <div className="mt-4 pl-8 space-y-3 animate-fade-in-up">
          <textarea
            placeholder="Add a description..."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            className="w-full resize-none text-sm"
          />
          <div className="flex items-center gap-2">
            <Flag className="h-4 w-4 text-[var(--text-muted)]" />
            <span className="text-sm text-[var(--text-secondary)]">Priority:</span>
            {(['low', 'medium', 'high'] as Priority[]).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPriority(p)}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
                  priority === p
                    ? PRIORITY_ACTIVE_CLASSES[p]
                    : 'bg-[var(--bg-elevated)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]'
                }`}
              >
                {capitalize(p)}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <Calendar className="h-4 w-4 text-[var(--text-muted)]" />
            <span className="text-sm text-[var(--text-secondary)]">Due date:</span>
            <input
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className="px-3 py-1 rounded-lg text-xs font-medium bg-[var(--bg-elevated)] text-[var(--text-secondary)] border border-[var(--border-primary)]"
            />
            {dueDate && (
              <button
                type="button"
                onClick={() => setDueDate('')}
                className="text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      )}
    </form>
  );
}

function StatsBar() {
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: () => api.getStats(),
    refetchInterval: 5000,
  });

  if (!stats) return null;

  const completionPct = stats.total > 0 ? Math.round((stats.completed / stats.total) * 100) : 0;

  return (
    <div className="grid grid-cols-4 gap-4">
      <div className="stat-card p-4">
        <div className="flex items-center gap-2 text-[var(--text-muted)] text-xs font-medium uppercase tracking-wider">
          <ListTodo className="h-3.5 w-3.5" />
          Total
        </div>
        <div className="mt-2 text-2xl font-bold text-[var(--text-primary)]">{stats.total}</div>
      </div>

      <div className="stat-card stat-card-success p-4">
        <div className="flex items-center gap-2 text-[var(--text-muted)] text-xs font-medium uppercase tracking-wider">
          <CheckCircle2 className="h-3.5 w-3.5" />
          Done
        </div>
        <div className="mt-2 text-2xl font-bold text-[var(--accent-success)]">{stats.completed}</div>
        {stats.total > 0 && (
          <div className="mt-2 w-full bg-[var(--bg-elevated)] rounded-full h-1.5">
            <div
              className="bg-[var(--accent-success)] h-1.5 rounded-full transition-all duration-500"
              style={{ width: `${completionPct}%` }}
            />
          </div>
        )}
      </div>

      <div className="stat-card stat-card-warning p-4">
        <div className="flex items-center gap-2 text-[var(--text-muted)] text-xs font-medium uppercase tracking-wider">
          <BarChart3 className="h-3.5 w-3.5" />
          Pending
        </div>
        <div className="mt-2 text-2xl font-bold text-[var(--accent-warning)]">{stats.pending}</div>
      </div>

      <div className="stat-card stat-card-danger p-4">
        <div className="flex items-center gap-2 text-[var(--text-muted)] text-xs font-medium uppercase tracking-wider">
          <Flag className="h-3.5 w-3.5" />
          High Priority
        </div>
        <div className="mt-2 text-2xl font-bold text-[var(--accent-danger)]">{stats.high_priority}</div>
      </div>
    </div>
  );
}

function EmptyState({ filter }: { filter: FilterMode }) {
  const messages = {
    all: { title: 'No todos yet', sub: 'Add your first task to get started' },
    active: { title: 'All caught up!', sub: 'No active tasks remaining' },
    completed: { title: 'Nothing completed yet', sub: 'Complete a task to see it here' },
  };
  const msg = messages[filter];

  return (
    <div className="empty-state text-center py-16">
      <Sparkles className="h-12 w-12 mx-auto text-[var(--accent-primary)] mb-4" />
      <h3 className="text-lg font-semibold text-[var(--text-primary)]">{msg.title}</h3>
      <p className="text-sm text-[var(--text-muted)] mt-1">{msg.sub}</p>
    </div>
  );
}

function AppContent() {
  const [filter, setFilter] = useState<FilterMode>('all');

  const { data: currentUser, isLoading: userLoading } = useQuery({
    queryKey: ['me'],
    queryFn: () => api.getMe(),
    staleTime: Infinity,
  });

  const completed = filter === 'all' ? undefined : filter === 'completed';
  const { data: todosData, isLoading: todosLoading } = useQuery({
    queryKey: ['todos', filter],
    queryFn: () => api.listTodos(completed),
    refetchInterval: 5000,
  });

  const todos = todosData?.todos ?? [];

  return (
    <div className="min-h-screen bg-[var(--bg-primary)]">
      <header className="bg-[var(--bg-secondary)] border-b border-[var(--border-primary)] sticky top-0 z-40">
        <div className="max-w-3xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-[var(--accent-primary)] rounded-xl">
                <ListTodo className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">
                  Lakebase Todo
                </h1>
                <p className="text-xs text-[var(--text-muted)] flex items-center gap-1">
                  <Database className="h-3 w-3" />
                  Powered by Databricks Lakebase
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 px-3 py-1.5 bg-[var(--bg-elevated)] border border-[var(--border-primary)] rounded-lg">
              <User className="h-4 w-4 text-[var(--accent-primary)]" />
              {userLoading ? (
                <div className="h-4 w-20 bg-[var(--bg-hover)] rounded animate-pulse" />
              ) : (
                <span className="text-sm font-medium text-[var(--text-secondary)]">
                  {currentUser?.display_name || 'Guest'}
                </span>
              )}
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <StatsBar />
        <AddTodoForm />

        <div className="flex items-center gap-1 p-1 bg-[var(--bg-elevated)] rounded-xl w-fit">
          {(['all', 'active', 'completed'] as FilterMode[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                filter === f
                  ? 'bg-[var(--bg-secondary)] text-[var(--text-primary)] shadow-sm'
                  : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
              }`}
            >
              {capitalize(f)}
            </button>
          ))}
        </div>

        <div className="space-y-2">
          {todosLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="card p-5">
                  <div className="flex items-center gap-4">
                    <div className="h-6 w-6 bg-[var(--bg-elevated)] rounded-full animate-pulse" />
                    <div className="flex-1 space-y-2">
                      <div className="h-4 w-3/4 bg-[var(--bg-elevated)] rounded animate-pulse" />
                      <div className="h-3 w-1/2 bg-[var(--bg-elevated)] rounded animate-pulse" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : todos.length === 0 ? (
            <EmptyState filter={filter} />
          ) : (
            todos.map((todo) => <TodoItem key={todo.id} todo={todo} />)
          )}
        </div>
      </main>

      <footer className="mt-8 py-6 border-t border-[var(--border-primary)]">
        <div className="max-w-3xl mx-auto px-6 flex items-center justify-center text-xs text-[var(--text-muted)] gap-1">
          <span>Lakebase Todo v0.1.0</span>
          <span className="mx-2">|</span>
          <Database className="h-3 w-3" />
          <span>Databricks Lakebase Autoscaling</span>
        </div>
      </footer>
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  );
}

export default App;

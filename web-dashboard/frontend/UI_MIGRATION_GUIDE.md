# UI Migration Guide - OriginUI + Tailwind CSS

## Overview

Frontend migrated from Material-UI to **Tailwind CSS v4 + OriginUI-inspired components** for a modern, performant, and lightweight UI.

## What Changed

### Before (Material-UI)
- Heavy dependency (~500KB gzipped)
- Predefined themes
- Component-based styling
- Limited customization

### After (Tailwind CSS + OriginUI)
- Lightweight (~21KB CSS gzipped)
- Utility-first CSS
- Full customization
- Modern OriginUI-inspired design

## New Component Structure

### Core UI Components

Located in `/src/components/ui/`:

1. **Card.jsx** - Container components
   ```jsx
   import { Card, CardHeader, CardTitle, CardDescription, CardContent } from './ui/Card';

   <Card>
     <CardHeader>
       <CardTitle>Title</CardTitle>
       <CardDescription>Description</CardDescription>
     </CardHeader>
     <CardContent>
       {/* Content */}
     </CardContent>
   </Card>
   ```

2. **Badge.jsx** - Status indicators
   ```jsx
   import { Badge } from './ui/Badge';

   <Badge variant="success">High Quality</Badge>
   <Badge variant="warning">Medium Risk</Badge>
   <Badge variant="danger">Critical</Badge>
   ```

3. **MetricCard.jsx** - Metrics display
   ```jsx
   import { MetricCard } from './ui/MetricCard';

   <MetricCard
     title="Quality Score"
     value={85}
     description="Overall quality"
     className="border-green-200"
   />
   ```

4. **Progress.jsx** - Progress indicators
   ```jsx
   import { QualityScore } from './ui/Progress';

   <QualityScore score={85} label="Overall Quality" />
   ```

### Utility Functions

Located in `/src/lib/utils.js`:

- `cn()` - Merge Tailwind classes
- `formatNumber()` - Format large numbers (1000 → 1K)
- `formatBytes()` - Format bytes (1024 → 1 KB)
- `getRiskColor()` - Get Tailwind classes for risk levels
- `getQualityBadge()` - Get badge info for quality levels

## Color System

### Custom Colors (via CSS Variables)

```css
--color-primary: 221.2 83.2% 53.3%;        /* Blue */
--color-secondary: 210 40% 96.1%;          /* Light gray */
--color-destructive: 0 84.2% 60.2%;        /* Red */
--color-muted: 210 40% 96.1%;              /* Muted gray */
--color-border: 214.3 31.8% 91.4%;         /* Border gray */
```

Usage in components:
```jsx
<div className="bg-primary text-primary-foreground">
  Primary background
</div>
```

## Dashboard Structure

### PipelineResultsDashboardNew.jsx

**Tabs:**
1. **Overview** - Quality scores, charts
2. **QC** - NanoPlot metrics
3. **Assembly** - Flye assembly stats
4. **MAGs** - CheckM binning results
5. **AMR** - Antibiotic resistance genes
6. **Taxonomy** - Kraken2 species

**Features:**
- Responsive grid layouts
- Interactive Recharts visualizations
- Dynamic status badges
- Formatted numbers/bytes
- Risk-based color coding

## Charts

Using **Recharts** (already installed):

```jsx
import { ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

<ResponsiveContainer width="100%" height={200}>
  <PieChart>
    <Pie
      data={amrRiskData}
      cx="50%"
      cy="50%"
      innerRadius={60}
      outerRadius={80}
      dataKey="value"
    >
      {amrRiskData.map((entry, index) => (
        <Cell key={`cell-${index}`} fill={entry.color} />
      ))}
    </Pie>
    <Tooltip />
    <Legend />
  </PieChart>
</ResponsiveContainer>
```

## Styling Guidelines

### Use Tailwind Utilities

```jsx
// Layout
<div className="flex items-center justify-between">

// Spacing
<div className="p-6 space-y-4">

// Typography
<h1 className="text-3xl font-bold">

// Colors
<div className="bg-blue-50 text-blue-800 border border-blue-200">

// Responsive
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
```

### Don't Mix Inline Styles

❌ Bad:
```jsx
<div style={{ padding: '20px' }} className="bg-white">
```

✅ Good:
```jsx
<div className="p-5 bg-white">
```

## Migration Checklist

- [x] Install Tailwind CSS v4 + PostCSS
- [x] Install utility libraries (clsx, tailwind-merge)
- [x] Create base UI components (Card, Badge, MetricCard, Progress)
- [x] Create utility functions (formatNumber, formatBytes, etc.)
- [x] Migrate PipelineResultsDashboard to Tailwind
- [x] Update index.css with Tailwind v4 config
- [x] Build and deploy to Docker
- [ ] Migrate PipelineDashboard
- [ ] Migrate ResultsViewer
- [ ] Add dark mode toggle (optional)
- [ ] Add more OriginUI components as needed

## Adding New Components

1. Create component in `/src/components/ui/`
2. Use `cn()` for class merging
3. Follow Tailwind naming conventions
4. Add to this guide

Example:
```jsx
import { cn } from '../../lib/utils';

export function Button({ className, variant = 'default', ...props }) {
  return (
    <button
      className={cn(
        "px-4 py-2 rounded-md transition",
        variant === 'default' && "bg-primary text-primary-foreground",
        variant === 'destructive' && "bg-destructive text-destructive-foreground",
        className
      )}
      {...props}
    />
  );
}
```

## Performance

### Before
- Bundle size: ~500KB (gzipped)
- CSS: ~100KB

### After
- Bundle size: ~336KB (gzipped)
- CSS: ~21KB (gzipped)

**Improvement: ~34% smaller bundle, ~79% smaller CSS**

## Resources

- [Tailwind CSS v4 Docs](https://tailwindcss.com/)
- [OriginUI Components](https://originui.com/)
- [Recharts Docs](https://recharts.org/)
- [class-variance-authority](https://cva.style/docs)

## Troubleshooting

### Build fails with Tailwind error
1. Ensure `@tailwindcss/postcss` is installed
2. Check `postcss.config.js` uses correct plugin
3. Verify `index.css` uses `@import "tailwindcss"`

### Classes not applying
1. Check class names are correct
2. Ensure component is in `content` array (all .jsx files)
3. Clear browser cache

### Colors not working
1. Verify CSS variables in `index.css`
2. Use `hsl(var(--color-primary))` format
3. Check Tailwind v4 `@theme` syntax

## Next Steps

1. ✅ Deployed to production
2. Test on http://100.72.39.49:3000/results/test_small_0201_v4
3. Migrate remaining components
4. Consider adding more OriginUI components from https://originui.com/

---

**Date:** January 2, 2026
**Version:** 1.0
**Author:** Claude Sonnet 4.5

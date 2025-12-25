// Assembly Quality Statistics Dashboard
// Displays N50, GC content, coverage, and QUAST metrics

import React from 'react';
import { Box, Paper, Typography, Grid, Card, CardContent } from '@mui/material';
import {
  Assessment as AssessmentIcon,
  Timeline as TimelineIcon,
  BubbleChart as BubbleChartIcon,
  CheckCircle as CheckCircleIcon
} from '@mui/icons-material';

function AssemblyStats({ stats }) {
  if (!stats) return null;

  const statCards = [
    {
      label: 'N50',
      value: stats.n50 ? `${(stats.n50 / 1000).toFixed(1)} kb` : 'N/A',
      icon: <BubbleChartIcon />,
      color: '#667eea'
    },
    {
      label: 'Total Length',
      value: stats.total_length ? `${(stats.total_length / 1000000).toFixed(2)} Mb` : 'N/A',
      icon: <TimelineIcon />,
      color: '#f093fb'
    },
    {
      label: 'GC Content',
      value: stats.gc_content ? `${stats.gc_content.toFixed(1)}%` : 'N/A',
      icon: <AssessmentIcon />,
      color: '#4facfe'
    },
    {
      label: 'Contigs',
      value: stats.num_contigs || 'N/A',
      icon: <CheckCircleIcon />,
      color: '#43e97b'
    },
    {
      label: 'L50',
      value: stats.l50 || 'N/A',
      icon: <BubbleChartIcon />,
      color: '#fa709a'
    },
    {
      label: 'Longest Contig',
      value: stats.longest_contig ? `${(stats.longest_contig / 1000).toFixed(1)} kb` : 'N/A',
      icon: <TimelineIcon />,
      color: '#30cfd0'
    }
  ];

  return (
    <Paper elevation={2} sx={{ p: 2 }}>
      <Typography variant="h6" gutterBottom>
        Assembly Quality Metrics
      </Typography>
      
      <Grid container spacing={2}>
        {statCards.map((stat, idx) => (
          <Grid item xs={12} sm={6} md={4} key={idx}>
            <Card 
              elevation={1}
              sx={{
                background: `linear-gradient(135deg, ${stat.color}22 0%, ${stat.color}11 100%)`,
                border: `1px solid ${stat.color}33`
              }}
            >
              <CardContent>
                <Box display="flex" alignItems="center" mb={1}>
                  <Box 
                    sx={{ 
                      color: stat.color, 
                      display: 'flex', 
                      mr: 1 
                    }}
                  >
                    {stat.icon}
                  </Box>
                  <Typography variant="body2" color="text.secondary">
                    {stat.label}
                  </Typography>
                </Box>
                <Typography variant="h5" component="div" sx={{ fontWeight: 600 }}>
                  {stat.value}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {stats.notes && (
        <Box mt={2}>
          <Typography variant="caption" color="text.secondary">
            {stats.notes}
          </Typography>
        </Box>
      )}
    </Paper>
  );
}

export default AssemblyStats;

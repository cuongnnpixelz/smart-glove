#pragma once
#include <math.h>
#include <stdint.h>
#include <stddef.h>

namespace GloveFeatures {
struct Sample {
  uint32_t stamp;
  double flex[5], acc[3], gyro[3], body[3];
};
struct Calibration { double opened[5], closed[5], bias[3], gravity; };

inline double median(double* a, int n) {
  for (int i = 1; i < n; ++i) {
    double v = a[i]; int j = i;
    while (j && a[j-1] > v) { a[j] = a[j-1]; --j; }
    a[j] = v;
  }
  return n % 2 ? a[n/2] : (a[n/2-1] + a[n/2]) / 2;
}
inline void multiply(const double* q, const double* r, double* out) {
  const double w=q[0], x=q[1], y=q[2], z=q[3];
  const double v=r[0], i=r[1], j=r[2], k=r[3];
  out[0]=w*v-x*i-y*j-z*k; out[1]=w*i+x*v+y*k-z*j;
  out[2]=w*j-x*k+y*v+z*i; out[3]=w*k+x*j-y*i+z*v;
}
inline void gravityBody(const double* q, double gravity, double* out) {
  out[0]=2*(q[1]*q[3]-q[0]*q[2])*gravity;
  out[1]=2*(q[2]*q[3]+q[0]*q[1])*gravity;
  out[2]=(1-2*(q[1]*q[1]+q[2]*q[2]))*gravity;
}
struct Imu {
  double q[4] = {1,0,0,0};
  uint32_t last=0, first=0; bool initialized=false;
  void reset() { initialized=false; }
  bool process(Sample& s, const Calibration& c) {
    double mag=sqrt(s.acc[0]*s.acc[0]+s.acc[1]*s.acc[1]+s.acc[2]*s.acc[2]);
    if (initialized && (s.stamp <= last || s.stamp-last > 20)) reset();
    if (!initialized) {
      if (!(mag > .8*c.gravity && mag < 1.2*c.gravity)) return false;
      double roll=atan2(s.acc[1],s.acc[2]);
      double pitch=atan2(-s.acc[0],hypot(s.acc[1],s.acc[2]));
      double cr=cos(roll/2), sr=sin(roll/2), cp=cos(pitch/2), sp=sin(pitch/2);
      q[0]=cr*cp; q[1]=sr*cp; q[2]=cr*sp; q[3]=-sr*sp;
      initialized=true; first=s.stamp;
    } else {
      double omega[4]={0,s.gyro[0]-c.bias[0],s.gyro[1]-c.bias[1],s.gyro[2]-c.bias[2]};
      if (mag > .8*c.gravity && mag < 1.2*c.gravity) {
        double expected[3]; gravityBody(q,1,expected);
        omega[1]+=2*(s.acc[1]*expected[2]-s.acc[2]*expected[1])/mag;
        omega[2]+=2*(s.acc[2]*expected[0]-s.acc[0]*expected[2])/mag;
        omega[3]+=2*(s.acc[0]*expected[1]-s.acc[1]*expected[0])/mag;
      }
      double delta[4]; multiply(q,omega,delta);
      double norm=0, dt=(s.stamp-last)/1000.0;
      for (int i=0;i<4;++i) { q[i]+=.5*delta[i]*dt; norm+=q[i]*q[i]; }
      norm=sqrt(norm); for (int i=0;i<4;++i) q[i]/=norm;
    }
    last=s.stamp;
    double gb[3]; gravityBody(q,c.gravity,gb);
    for (int i=0;i<3;++i) s.body[i]=s.acc[i]-gb[i];
    return s.stamp-first >= 2000;
  }
};

// Actual sample timestamps are interpolated to 0,10,...1490 ms, as in Python.
// Caller supplies reusable workspace to avoid large stacks and heap allocation.
inline bool build(const Sample* rows, const Calibration& c, float* out,
                  double (*grid)[14], double (*flex)[5]) {
  if (c.gravity <= 0) return false;
  for (int k=0;k<5;++k)
    if (!isfinite(c.opened[k]) || !isfinite(c.closed[k]) || c.opened[k]-c.closed[k]<15) return false;
  for (int i=0;i<150;++i) {
    if (i && (rows[i].stamp<=rows[i-1].stamp || rows[i].stamp-rows[i-1].stamp>20)) return false;
    for (int k=0;k<5;++k) if (!isfinite(rows[i].flex[k]) || rows[i].flex[k]<=8 || rows[i].flex[k]>=4087) return false;
    for (int k=0;k<3;++k)
      if (!isfinite(rows[i].acc[k]) || !isfinite(rows[i].gyro[k]) || !isfinite(rows[i].body[k])) return false;
  }
  uint32_t span=rows[149].stamp-rows[0].stamp;
  if (span<1490 || span>1510) return false;
  int pos=0;
  for (int i=0;i<150;++i) {
    double t=i*10;
    while (pos<148 && rows[pos+1].stamp-rows[0].stamp<t) ++pos;
    double weight=(t-(rows[pos].stamp-rows[0].stamp))/double(rows[pos+1].stamp-rows[pos].stamp);
    for (int k=0;k<14;++k) {
      const Sample& a=rows[pos]; const Sample& b=rows[pos+1];
      double v0=k<5?a.flex[k]:k<8?a.acc[k-5]:k<11?a.gyro[k-8]:a.body[k-11];
      double v1=k<5?b.flex[k]:k<8?b.acc[k-5]:k<11?b.gyro[k-8]:b.body[k-11];
      grid[i][k]=v0+weight*(v1-v0);
    }
  }
  for (int i=0;i<150;++i) for (int k=0;k<5;++k) {
    double window[5]; int n=0;
    for (int j=(i>1?i-2:0); j<150 && j<=i+2; ++j) window[n++]=grid[j][k];
    flex[i][k]=(median(window,n)-c.opened[k])/(c.closed[k]-c.opened[k]);
  }
  for (int i=0;i<150;++i) {
    int left=i>1?i-2:0, right=i<148?i+2:149;
    for (int k=0;k<5;++k) out[i*19+k]=float(flex[i][k]);
    for (int k=0;k<3;++k) {
      out[i*19+5+k]=float((grid[i][5+k]-grid[i][11+k])/c.gravity);
      out[i*19+8+k]=float(grid[i][8+k]-c.bias[k]);
      out[i*19+11+k]=float(grid[i][11+k]);
    }
    for (int k=0;k<5;++k)
      out[i*19+14+k]=float((flex[right][k]-flex[left][k])/((right-left)*.01));
  }
  return true;
}
}

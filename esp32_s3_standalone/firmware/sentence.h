#pragma once
#include <string.h>
#include "model.h"
#include "config.h"

// Match the current Python run filter, including its user-specific exceptions.
// No text-to-speech or cloud access is performed here.
struct Sentence {
  struct Run { int label, count; } runs[128];
  int size=0, noneCount=0; bool active=false;
  int id(const char* name) const {
    for (int i=0;i<15;++i) if (!strcmp(GloveModel::LABELS[i],name)) return i;
    return -1;
  }
  int minimum(int label) const {
    const char* s=GloveModel::LABELS[label];
    if (!strcmp(s,"DI_DAU") || !strcmp(s,"O_DAU") || !strcmp(s,"TUYET_VOI")) return 4;
    if (!strcmp(s,"CAM_ON") || !strcmp(s,"TEN")) return 3;
    return SENTENCE_MIN_VOTES;
  }
  void reset() { size=noneCount=0; active=false; }
  // 0: collecting, 1: finished, -1: bounded buffer overflow (discard).
  int push(int label) {
    if (!active && label==id("NONE")) return 0;
    active=true;
    if (size && runs[size-1].label==label) ++runs[size-1].count;
    else {
      if (size==128) { reset(); return -1; }
      runs[size++]={label,1};
    }
    noneCount=label==id("NONE")?noneCount+1:0;
    return noneCount>=NONE_END_WINDOWS?1:0;
  }
  int words(int* out) const {
    Run corrected[128]; memcpy(corrected,runs,size*sizeof(Run));
    const int ban=id("BAN"), gi=id("GI"), ten=id("TEN"), toi=id("TOI");
    const int buon=id("BUON_BA"), khoe=id("KHOE"), none=id("NONE");
    const int tuyet=id("TUYET_VOI"), di=id("DI_DAU"), dau=id("O_DAU"), chao=id("CHAO");
    for (int start=0;start<size;++start) {
      if (runs[start].label!=ban || runs[start].count<SENTENCE_MIN_VOTES) continue;
      for (int end=start+1;end<size;++end) {
        int label=runs[end].label;
        if (label==gi && runs[end].count>=SENTENCE_MIN_VOTES) {
          bool hasTen=false, allowed=true; int support=0;
          for (int j=start+1;j<end;++j) {
            int w=runs[j].label,n=runs[j].count;
            hasTen|=w==ten && n>=minimum(ten);
            allowed&=w==ten || w==toi || ((w==buon || w==khoe) && n<SENTENCE_MIN_VOTES);
            if (w==ten || w==toi) support+=n;
          }
          if (hasTen && allowed && support>=SENTENCE_MIN_VOTES) {
            for (int j=start+1;j<end;++j) if (corrected[j].label==toi) corrected[j].label=ten;
            corrected[start+1]={ten,support};
          }
          break;
        }
        if (label!=ten && label!=toi && label!=buon && label!=khoe) break;
      }
    }
    int count=0;
    auto append=[&](int label) { if (!count || out[count-1]!=label) out[count++]=label; };
    for (int i=0;i<size;) {
      if (i+3<size && corrected[i].label==id("AN") && corrected[i].count==5 &&
          corrected[i+1].label==tuyet && corrected[i+1].count==3 &&
          corrected[i+2].label==dau && corrected[i+2].count==1 &&
          corrected[i+3].label==buon && corrected[i+3].count==3) {
        append(tuyet); i+=4; continue;
      }
      if (i+2<size && corrected[i].label==di && corrected[i].count>=4 &&
          corrected[i+1].label==khoe && corrected[i+1].count>=2 &&
          corrected[i+2].label==chao && corrected[i+2].count>=SENTENCE_MIN_VOTES) {
        append(khoe); i+=3; continue;
      }
      int next=i+1;
      while (next<size && corrected[next].label!=none && corrected[next].count<minimum(corrected[next].label)) ++next;
      if (next<size && corrected[i].label==tuyet && corrected[i].count>=minimum(tuyet) && corrected[next].label==buon) {
        append(tuyet); i=next+1; continue;
      }
      if (next<size && corrected[i].label==di && corrected[i].count>=minimum(di) &&
          corrected[next].label==dau && corrected[next].count>=minimum(dau)) {
        append(dau); i=next+1; continue;
      }
      int label=corrected[i].label,n=corrected[i].count; ++i;
      if (label!=none && n>=minimum(label)) append(label);
    }
    bool onlyChao=true; int wave=0;
    for (int i=0;i<size;++i) {
      if (runs[i].label!=none && runs[i].label!=chao) onlyChao=false;
      if (runs[i].label==chao && runs[i].count>=2) wave+=runs[i].count;
    }
    if (!count && onlyChao && wave>=(SENTENCE_MIN_VOTES>4?SENTENCE_MIN_VOTES:4)) append(chao);
    return count;
  }
};

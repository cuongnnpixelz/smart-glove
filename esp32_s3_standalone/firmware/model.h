#pragma once
#include <stdint.h>
#include <stddef.h>

namespace GloveModel {
constexpr size_t CLASS_COUNT = 15, TREE_COUNT = 300, NODE_COUNT = 47966;
constexpr size_t STEP_COUNT = 150, FEATURE_COUNT = 19, INPUT_COUNT = 2850;
struct Node { float threshold; uint16_t feature, left, right; };
static_assert(sizeof(Node) == 12, "Unexpected model node layout");
extern const Node NODES[NODE_COUNT];
extern const uint16_t ROOTS[TREE_COUNT];
extern const char* const LABELS[CLASS_COUNT];

inline int predict(const float* features, uint16_t* votes) {
  for (size_t c = 0; c < CLASS_COUNT; ++c) votes[c] = 0;
  for (size_t t = 0; t < TREE_COUNT; ++t) {
    uint16_t node = ROOTS[t];
    while (NODES[node].feature != 65535) {
      const Node& n = NODES[node];
      node = features[n.feature] <= n.threshold ? n.left : n.right;
    }
    ++votes[NODES[node].left];
  }
  int best = 0;
  for (size_t c = 1; c < CLASS_COUNT; ++c)
    if (votes[c] > votes[best]) best = c;
  return best;
}
}

using UnityEngine;

namespace ZGame.UnityDraft.Systems
{
    [CreateAssetMenu(fileName = "ObstacleSet", menuName = "ZGame/ObstacleSet")]
    public class ObstacleSet : ScriptableObject
    {
        public GameObject[] solids;
        public GameObject[] destructibles;
        public GameObject[] decor;
    }
}

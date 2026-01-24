using UnityEngine;
#if UNITY_AI_NAVIGATION
using Unity.AI.Navigation;
#endif

namespace ZGame.UnityDraft.Nav
{
    /// <summary>
    /// Stub for 2D NavMesh integration using NavMeshComponents.
    /// This assumes you are using the NavMeshSurface (projected on XY) and NavMeshAgent on enemies.
    /// </summary>
    public class NavMesh2DStub : MonoBehaviour
    {
#if UNITY_AI_NAVIGATION
        public NavMeshSurface navSurface;
        public bool autoBuild = true;

        private void Awake()
        {
            if (navSurface == null)
            {
                navSurface = GetComponent<NavMeshSurface>();
            }
            if (navSurface != null)
            {
                navSurface.collectObjects = CollectObjects.Children;
                navSurface.useGeometry = NavMeshCollectGeometry.PhysicsColliders;
                navSurface.overrideTileSize = true;
                navSurface.tileSize = 16;
                navSurface.layerMask = ~0; // include all by default
            }
        }

        private void Start()
        {
            if (autoBuild && navSurface != null)
            {
                navSurface.BuildNavMesh();
            }
        }

        public void Rebuild()
        {
            if (navSurface != null)
            {
                navSurface.BuildNavMeshAsync();
            }
        }
#else
        private void Awake()
        {
            Debug.LogWarning("NavMeshComponents package not present. Install Unity.AI.Navigation to enable NavMesh2D.");
        }
#endif
    }
}

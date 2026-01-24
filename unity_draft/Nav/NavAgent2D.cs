using UnityEngine;
#if UNITY_AI_NAVIGATION
using UnityEngine.AI;
#endif

namespace ZGame.UnityDraft.Nav
{
    /// <summary>
    /// Wrapper to drive a NavMeshAgent on a 2D plane (XY).
    /// </summary>
    [RequireComponent(typeof(Enemy))]
    public class NavAgent2D : MonoBehaviour
    {
#if UNITY_AI_NAVIGATION
        public Transform target;
        public float repathInterval = 0.25f;

        private NavMeshAgent _agent;
        private float _timer;

        private void Awake()
        {
            _agent = GetComponent<NavMeshAgent>();
            if (_agent != null)
            {
                _agent.updateUpAxis = false;
                _agent.updateRotation = false;
            }
        }

        private void Start()
        {
            if (target == null)
            {
                var p = FindObjectOfType<Player>();
                if (p != null) target = p.transform;
            }
        }

        private void Update()
        {
            if (_agent == null || target == null) return;
            _timer -= Time.deltaTime;
            if (_timer <= 0f)
            {
                _agent.SetDestination(target.position);
                _timer = repathInterval;
            }
        }
#else
        private void Awake()
        {
            Debug.LogWarning("NavMeshComponents package not present. Install Unity.AI.Navigation to enable NavMesh2D agents.");
        }
#endif
    }
}

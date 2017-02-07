"""
Implements a concrete DeployOperation class.
"""

# Domain Services
from cloudshell.cp.openstack.domain.services.nova.nova_instance_service import NovaInstanceService

# Results
from cloudshell.cp.openstack.models.deploy_result_model import DeployResultModel

import traceback

class DeployOperation(object):
    def __init__(self, instance_service, cancellation_service):
        """

        :param NovaInstanceService instance_service:
        :param cancellation_service:
        """
        self.cancellation_service = cancellation_service
        self.instance_service = instance_service

    def deploy(self, os_session, name, reservation, cp_resource_model, deploy_req_model, cancellation_context, logger):
        """
        Performs actual deploy operation.
        :param keystoneauth1.session.Session os_session:
        :param str name: Name of the instance to be deployed
        :param ReservationModel reservation:
        :param DeployDataHolder deploy_req_model:
        :param OpenStackResourceModel cp_resource_model:
        :param cancellation_context:
        :param LoggingSessionContext logger:
        :rtype DeployResultModel:
        """
        logger.info("Inside Deploy Operation.")
        # First create instance
        instance = None
        floating_ip = ''
        try:
            # Look for right at the beginning -- ???    
            self.cancellation_service.check_if_cancelled(cancellation_context=cancellation_context)

            instance = self.instance_service.create_instance(openstack_session=os_session,
                                                         name=name,
                                                         reservation=reservation,
                                                         cp_resource_model=cp_resource_model,
                                                         deploy_req_model=deploy_req_model,
                                                         cancellation_context=cancellation_context,
                                                         logger=logger)

            # Actually cannot come here and instance is None. If the previous statement raised an Exception,
            # we'd deal with it in the except cause.
            if instance is None:
                raise ValueError("Create Instance Returned None")

            logger.info("Deploy Operation Done. Instance Created: {0}:{1}".format(instance.name,instance.id))

        # Get Private Network
            private_network_name = self.instance_service.get_instance_mgmt_network_name(instance=instance,
                                                                                        openstack_session=os_session,
                                                                                        cp_resource_model=cp_resource_model)
            if private_network_name is None:
                raise ValueError("Management network with ID for instance not found". \
                                 format(cp_resource_model.qs_mgmt_os_net_id))

        # Assign floating IP
            if deploy_req_model.add_floating_ip:
                if deploy_req_model.external_network_uuid:
                    floating_ip_net_uuid = deploy_req_model.external_network_uuid
                else:
                    floating_ip_net_uuid = cp_resource_model.external_network_uuid

                floating_ip = self.instance_service.assign_floating_ip(instance=instance,
                                                                       openstack_session=os_session,
                                                                       cp_resource_model=cp_resource_model,
                                                                       floating_ip_net_uuid=floating_ip_net_uuid,
                                                                       logger=logger)
            # Get private IP
            private_ip_address = self.instance_service.get_private_ip(instance, private_network_name)

            deployed_app_attributes = dict()
            deployed_app_attributes['Public IP'] = floating_ip

            # Just make sure we were not cancelled before returning result.
            self.cancellation_service.check_if_cancelled(cancellation_context=cancellation_context)

            return DeployResultModel(vm_name=instance.name,
                                     vm_uuid=instance.id,
                                     cloud_provider_name=deploy_req_model.cloud_provider,
                                     deployed_app_ip=private_ip_address,
                                     deployed_app_attributes=deployed_app_attributes,
                                     floating_ip=floating_ip)

        # If any Exception is raised during deploy or assign floating IP - clean up OpenStack side and re-raise
        except Exception as e:
            logger.error(traceback.format_exc())
            if instance:
                instance_id = instance.id
                # This calls detach and delete floating IP and instance terminate (handles empty floating IP)
                self.instance_service.terminate_instance(openstack_session=os_session,
                                                         instance_id=instance_id,
                                                         floating_ip=floating_ip,
                                                         logger=logger)


            # Re-raise for the UI
            raise
import glob
import shutil
from unit.common import DistributedTest
from unit.checkpoint.common import *
from unit.simple_model import *
import pytest
import json

class TestNebulaCheckpoint(DistributedTest):
    world_size = 1

    # @pytest.mark.parametrize('zero_stage', [3])
    # def test_save_16bit_model(self, tmpdir, zero_stage):
    #     config_dict = {
    #         "optimizer": {
    #             "type": 'Adam'
    #         },
    #         "fp16": {
    #             "enabled": True,
    #             "initial_scale_power": 8
    #         },
    #         "zero_optimization": {
    #             "stage": zero_stage,
    #             "stage3_gather_fp16_weights_on_model_save": True,
    #         },
    #         "gradient_accumulation_steps": 1,
    #         "train_micro_batch_size_per_gpu": 1,
    #         "train_batch_size": 4,
    #         "nebula": {
    #             "enabled": True,
    #             "persistent_storage_path": "/tmp/nebula_checkpoint/",
    #             "persistent_time_interval": 10,
    #             "num_of_version_in_retention": 2,
    #             "enable_nebula_load": True
    #         }
    #     }
    #     hidden_dim = 10
    #     models = [SimpleModel(hidden_dim=hidden_dim) for _ in range(2)]

    #     ds_model = create_deepspeed_model(config_dict=config_dict,
    #                                       model=models[0],
    #                                       base_optimizer=None)

    #     data_loader = random_dataloader(model=ds_model,
    #                                     total_samples=2,
    #                                     hidden_dim=hidden_dim,
    #                                     device=ds_model.device,
    #                                     dtype=torch.half)

    #     batch = next(iter(data_loader))
    #     loss = ds_model(batch[0], batch[1])
    #     ds_model.backward(loss)
    #     ds_model.step()

    #     save_folder = os.path.join(tmpdir, 'save_16bit_model')
    #     save_tag = None
    #     ds_model.save_16bit_model(save_folder)
        
    #     loaded_model = create_deepspeed_model(config_dict=config_dict,
    #                                         model=models[1],
    #                                         base_optimizer=None)
        
    #     assert list(ds_model.parameters())[0].dtype == list(loaded_model.parameters())[0].dtype

    #     loaded_model.load_checkpoint(tmpdir,
    #                                  tag=save_tag)

    #     compare_model_states(ds_model,
    #                          loaded_model)
        
    def test_save_checkpoint(self, tmpdir):
        print("list /dev/shm origin status: ", os.listdir("/dev/shm/"))
        for filename in glob.glob("/dev/shm/shm_name_partition_*"):
            os.remove(filename) 
        print("list /dev/shm before save: ", os.listdir("/dev/shm/"))  

        files = os.listdir("/tmp/nebula_checkpoint/")
        print("list /tmp/nebula_checkpoint/ before remove: ", files)
        if files != []:
            shutil.rmtree("/tmp/nebula_checkpoint/")
        config_dict = {
            "train_batch_size": 2,
            "steps_per_print": 1,
            "optimizer": {
                "type": "Adam",
                "params": {
                    "lr": 0.00015
                }
            },
            "nebula": {
                "enabled": True,
                "persistent_storage_path": "/tmp/nebula_checkpoint/",
                "persistent_time_interval": 10,
                "num_of_version_in_retention": 2,
                "enable_nebula_load": True
            }
        }
        hidden_dim = 10
        models = [SimpleModel(hidden_dim=hidden_dim) for _ in range(2)]
        dtype = torch.float32
        ds_model = create_deepspeed_model(config_dict=config_dict,
                                        model=models[0],
                                        base_optimizer=None)

        data_loader = random_dataloader(model=ds_model,
                                        total_samples=50,
                                        hidden_dim=hidden_dim,
                                        device=ds_model.device,
                                        dtype=dtype)


        for _, batch in enumerate(data_loader):
            loss = ds_model(batch[0], batch[1])
            ds_model.backward(loss)
            ds_model.step()

        trained_model = ds_model

        save_folder = os.path.join(tmpdir, 'saved_checkpoint')
        save_tag = None   
        
        trained_model.save_checkpoint(save_folder, tag=save_tag)
        print("list /dev/shm after save: ", os.listdir("/dev/shm/"))
        dist.barrier()

        loaded_model = create_deepspeed_model(config_dict=config_dict,
                                            model=models[1],
                                            base_optimizer=None)
        
        assert list(trained_model.parameters())[0].dtype == list(
            loaded_model.parameters())[0].dtype
        
        import torch_nebula as tn
        
        tn.flush_persistence()
        for root, dirs, files in os.walk("/tmp/nebula_checkpoint/", topdown=False):
            for name in files:
                print(os.path.join(root, name))
            for name in dirs:
                print(os.path.join(root, name))
        global_tag_ckpt = tn.list_checkpoints()
        js = json.dumps(global_tag_ckpt, sort_keys=True, indent=4, separators=(",", ":"))
        print(js)

        # get latest checkpoints by name
        latest_ckpt = tn.get_latest_checkpoint()
        print("latest_ckpt: ", latest_ckpt.tag)
        loaded_model.load_checkpoint(save_folder,
                                    tag=save_tag)

        compare_model_states(trained_model,
                            loaded_model,
                            compare_optimizer=True,
                            load_module_only=False)